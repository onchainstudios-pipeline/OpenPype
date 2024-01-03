import pyblish.api
from openpype.pipeline import Anatomy
from typing import Tuple, Union, List
from openpype.plugins import publish


class TimeData:
    start: int
    end: int
    fps: float | int
    step: int
    handle_start: int
    handle_end: int

    def __init__(self, start: int, end: int, fps: float | int, step: int, handle_start: int, handle_end: int):
        ...
    ...

def remap_source(source: str, anatomy: Anatomy): ...
def extend_frames(asset: str, subset: str, start: int, end: int) -> Tuple[int, int]: ...
def get_time_data_from_instance_or_context(instance: pyblish.api.Instance) -> TimeData: ...
def get_transferable_representations(instance: pyblish.api.Instance) -> list: ...
def create_skeleton_instance(instance: pyblish.api.Instance, families_transfer: list = ..., instance_transfer: dict = ...) -> dict: ...
def create_instances_for_aov(instance: pyblish.api.Instance, skeleton: dict, aov_filter: dict) -> List[pyblish.api.Instance]: ...
def attach_instances_to_subset(attach_to: list, instances: list) -> list: ...
def prepare_representations(skeleton_data: dict, exp_files: list,
                            anatomy: Anatomy, aov_filter: dict,
                            skip_integration_repre_list: list,
                            do_not_add_review: bool,
                            context: pyblish.api.Context,
                            color_managed_plugin: publish.ColormanagedPyblishPluginMixin) -> list: ...  # noqa: E501
def create_metadata_path(instance: pyblish.api.Instance, anatomy: Anatomy) -> str: ...  # noqa: E501
