#
# Copyright (C) 2023, Inria
# GRAPHDECO research group, https://team.inria.fr/graphdeco
# All rights reserved.
#
# This software is free for non-commercial, research and evaluation use 
# under the terms of the LICENSE.md file.
#
# For inquiries contact  george.drettakis@inria.fr
#

import os
import random
import json
from utils.system_utils import searchForMaxIteration
from scene.dataset_readers import sceneLoadTypeCallbacks
from scene.gaussian_model import GaussianModel
from arguments import ModelParams
from utils.camera_utils import cameraList_from_camInfos, camera_to_JSON, load_cam_info
from tqdm import tqdm
from typing import Union, List, Dict

import numpy as np

class Scene:

    gaussians : GaussianModel

    def __init__(self, args : ModelParams, gaussians : GaussianModel, load_iteration=None, shuffle=True, resolution_scales=[1.0],
                  llffhold=8, override_train_idxs=None, override_test_idxs=None):
        """b
        :param path: Path to colmap scene main folder.
        """
        self.model_path = args.model_path
        self.loaded_iter = None
        self.gaussians = gaussians

        if load_iteration:
            if load_iteration == -1:
                self.loaded_iter = searchForMaxIteration(os.path.join(self.model_path, "point_cloud"))
            else:
                self.loaded_iter = load_iteration
            print("Loading trained model at iteration {}".format(self.loaded_iter))

        self.train_cameras = {}
        self.test_cameras = {}
        self.num_cameras = 0

        if os.path.exists(os.path.join(args.source_path, "sparse")):
            scene_info = sceneLoadTypeCallbacks["Colmap"](args.source_path, args.images, args.eval, 
                                                          llffhold=llffhold, override_train_idxs=override_train_idxs, override_test_idxs=override_test_idxs)
        elif os.path.exists(os.path.join(args.source_path, "transforms_train.json")):
            print("Found transforms_train.json file, assuming Blender data set!")
            scene_info = sceneLoadTypeCallbacks["Blender"](args.source_path, args.white_background, args.eval)
        else:
            assert False, "Could not recognize scene type!"

        if not self.loaded_iter:
            with open(scene_info.ply_path, 'rb') as src_file, open(os.path.join(self.model_path, "input.ply") , 'wb') as dest_file:
                dest_file.write(src_file.read())
            json_cams = []
            camlist = []
            if scene_info.test_cameras:
                camlist.extend(scene_info.test_cameras)
            if scene_info.train_cameras:
                camlist.extend(scene_info.train_cameras)
            for id, cam in enumerate(camlist):
                json_cams.append(camera_to_JSON(id, cam))
            with open(os.path.join(self.model_path, "cameras.json"), 'w') as file:
                json.dump(json_cams, file)

        num_views = len(scene_info.train_cameras)
        self.all_train_set = set(range(num_views))
        self.train_idxs = list(range(num_views))
        self.num_cameras = num_views + len(scene_info.test_cameras)
        if shuffle:
            # Make this determinisjtic
            random.Random(42).shuffle(self.train_idxs)
            # The scene_info doesn't need to be shuffled 
            # random.Random(42).shuffle(scene_info.train_cameras)
            random.shuffle(scene_info.test_cameras)  # Multi-res consistent random shuffling

        self.cameras_extent = scene_info.nerf_normalization["radius"]

        for resolution_scale in resolution_scales:
            print("Loading Training Cameras")
            self.train_cameras[resolution_scale] = cameraList_from_camInfos(scene_info.train_cameras, resolution_scale, args)
            print("Loading Test Cameras")
            self.test_cameras[resolution_scale] = cameraList_from_camInfos(scene_info.test_cameras, resolution_scale, args)

        if self.loaded_iter:
            self.gaussians.load_ply(os.path.join(self.model_path,
                                                           "point_cloud",
                                                           "iteration_" + str(self.loaded_iter),
                                                           "point_cloud.ply"))
        else:
            self.gaussians.create_from_pcd(scene_info.point_cloud, self.cameras_extent)
        
        self.candidate_views_filter = None

    def save(self, iteration):
        point_cloud_path = os.path.join(self.model_path, "point_cloud/iteration_{}".format(iteration))
        self.gaussians.save_ply(os.path.join(point_cloud_path, "point_cloud.ply"))

    def getTrainCameras(self, scale=1.0):
        return self.train_cameras[scale]
    
    def getTrainImageNames(self, scale=1.0):
        return [i.image_name for i in self.train_cameras[scale]]

    def getTestCameras(self, scale=1.0):
        return self.test_cameras[scale]
    
    def getNumCameras(self):
        return self.num_cameras
    
    def get_candidate_set(self):
        # Get candidate set 
        # Ensure resutls are always the same
        candidate_set = sorted(list(self.all_train_set - set(self.train_idxs)))
        if self.candidate_views_filter is not None:
            candidate_set = list(filter(self.candidate_views_filter, candidate_set))
        return candidate_set

    def getCandidateCameras(self, scale=1.0):
        candidate_set = list(self.get_candidate_set())
        filted_train_camers = [self.train_cameras[scale][i] for i in candidate_set]
        return filted_train_camers
    
    def load_inflated_cameras(self, info_path: str, inflate_skip: int):
        with open(info_path, "r") as f:
            info_dict = json.load(f)

        base_path = os.path.dirname(info_path)

        for scale in self.train_cameras.keys():
            assert scale == 1., "Didn't implement for other scale"
            base_idx = max(self.all_train_set) + 1

            load_idxs = [idx for idx in range(len(info_dict)) if idx % inflate_skip == 0]
            load_dicts = [info_dict[i] for i in load_idxs]

            inflated_cams = [load_cam_info(d, base_path=base_path) for d in tqdm(load_dicts, desc="Loading inflated cams")]

            self.all_train_set.update([base_idx + i for i, _ in enumerate(load_idxs)])
            self.train_cameras[scale].extend(inflated_cams)

    def add_camera(self, camera, scale=1.0):
        """
        Add a new camera to the scene's training set.
        
        Args:
            camera: Camera object to add
            scale: Resolution scale (default: 1.0)
            
        Returns:
            int: Index of added camera
            
        Raises:
            ValueError: If scale not in camera dictionary
        """
        if scale not in self.train_cameras:
            raise ValueError(f"Scale {scale} not found in camera dictionary")
            
        idx = camera.uid
        self.train_cameras[scale].append(camera)
        self.all_train_set.add(idx)
        self.train_idxs.append(idx)  # Add to current training set
        return idx

    def update_cameras(self, train_indices: Union[List, Dict], test_indices: List, scale : float = 1.0):
        """Update cameras after they are filtered by the Schema"""

        all_cameras = self.train_cameras[scale]

        if isinstance(train_indices, list):
            self.train_cameras[scale] = [all_cameras[i] for i in train_indices]
        else:
            matched_idx = []
            train_names = set(train_indices.values())
            for cam in all_cameras:
                if cam.image_name in train_names:
                    matched_idx.append(cam.uid)
            self.train_cameras[scale] = [all_cameras[i] for i in matched_idx]
        
        # If the amount of images are over the total amount of images in the base dataset add them to the train set
        self.test_cameras[scale] = [all_cameras[i] for i in test_indices]
        del all_cameras
        # Reset indices for Train cameras
        for new_idx, cam in enumerate(self.train_cameras[scale]):
            cam.uid = new_idx
        for new_idx, cam in enumerate(self.test_cameras[scale]):
            cam.uid = new_idx
        self.train_idxs = list(range(0, len(train_indices)))
        self.test_idxs = list(range(0, len(test_indices)))