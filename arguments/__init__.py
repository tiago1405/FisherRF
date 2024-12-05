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

# Modified by Tiago Da Costa 02/12/2024 (dd/mm/yyyy)
# To accept dict and argparser

from argparse import ArgumentParser, Namespace
import sys
import os

class GroupParams:
    pass

class ParamGroup:
    def __init__(self, parser_or_dict, name: str, fill_none=False):
        if isinstance(parser_or_dict, dict):
            for key, value in parser_or_dict.items():
                if key.startswith("_"):
                    key = key[1:]
                setattr(self, key, value)
        else:
            group = parser_or_dict.add_argument_group(name)
            for key, value in vars(self).items():
                shorthand = False
                if key.startswith("_"):
                    shorthand = True
                    key = key[1:]
                t = type(value)
                value = value if not fill_none else None 
                if shorthand:
                    if t == bool:
                        group.add_argument("--" + key, ("-" + key[0:1]), default=value, action="store_true")
                    else:
                        group.add_argument("--" + key, ("-" + key[0:1]), default=value, type=t)
                else:
                    if t == bool:
                        group.add_argument("--" + key, default=value, action="store_true")
                    else:
                        group.add_argument("--" + key, default=value, type=t)

    def extract(self, args_or_dict):
        # Modified extract just handles the '_' infront of some of these variables when extracting
        group = GroupParams()
        if isinstance(args_or_dict, dict):
            for key, value in vars(self).items():
                stripped_key = key[1:] if key.startswith('_') else key
                if stripped_key in args_or_dict:
                    setattr(group, stripped_key, args_or_dict[stripped_key])
                else:
                    setattr(group, stripped_key, value)
        else:
            for arg in vars(args_or_dict).items():
                if arg[0] in vars(self) or ("_" + arg[0]) in vars(self):
                    setattr(group, arg[0], arg[1])
        return group

class ModelParams(ParamGroup):
    def __init__(self, parser_or_dict, sentinel=False):
        self.sh_degree = 3
        self._source_path = ""
        self._model_path = ""
        self._images = "images"
        self._resolution = -1
        self._white_background = False
        self.data_device = "cuda"
        self.eval = False
        super().__init__(parser_or_dict, "Loading Parameters", sentinel)

    def extract(self, args_or_dict):
        g = super().extract(args_or_dict)
        if hasattr(g, 'source_path'):
            g.source_path = os.path.abspath(g.source_path)
        return g

class PipelineParams(ParamGroup):
    def __init__(self, parser_or_dict):
        self.convert_SHs_python = False
        self.compute_cov3D_python = False
        self.debug = False
        super().__init__(parser_or_dict, "Pipeline Parameters")

class OptimizationParams(ParamGroup):
    def __init__(self, parser_or_dict):
        self.iterations = 30_000
        self.position_lr_init = 0.00016
        self.position_lr_final = 0.0000016
        self.position_lr_delay_mult = 0.01
        self.position_lr_max_steps = 30_000
        self.feature_lr = 0.0025
        self.opacity_lr = 0.05
        self.scaling_lr = 0.005
        self.rotation_lr = 0.001
        self.percent_dense = 0.01
        self.lambda_dssim = 0.2
        self.densification_interval = 100
        self.opacity_reset_interval = 3000
        self.densify_from_iter = 500
        self.densify_until_iter = 10_000
        self.densify_grad_threshold = 0.0002
        super().__init__(parser_or_dict, "Optimization Parameters")

def get_combined_args(parser: ArgumentParser):
    cmdlne_string = sys.argv[1:]
    cfgfile_string = "Namespace()"
    args_cmdline = parser.parse_args(cmdlne_string)

    try:
        cfgfilepath = os.path.join(args_cmdline.model_path, "cfg_args")
        print("Looking for config file in", cfgfilepath)
        with open(cfgfilepath) as cfg_file:
            print("Config file found: {}".format(cfgfilepath))
            cfgfile_string = cfg_file.read()
    except TypeError:
        print("Config file not found at")
        pass
    args_cfgfile = eval(cfgfile_string)

    merged_dict = vars(args_cfgfile).copy()
    for k,v in vars(args_cmdline).items():
        if v != None:
            merged_dict[k] = v
    return Namespace(**merged_dict)