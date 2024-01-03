import os
import re
import csv
import clique
from copy import deepcopy, copy

from openpype.client import get_asset_by_name
from openpype.pipeline.create import get_subset_name
from openpype.pipeline import CreatedInstance
from openpype.lib import FileDef, BoolDef
from openpype.lib.local_settings import get_openpype_username
from openpype.lib.transcoding import (
    VIDEO_EXTENSIONS, IMAGE_EXTENSIONS
)

from openpype.hosts.traypublisher.api.plugin import (
    TrayPublishCreator
)


class IngestCSV(TrayPublishCreator):
    """Editorial CSV creator class"""

    icon = "fa.file"

    label = "CSV Ingest"
    family = "editorialcsv"
    identifier = "io.openpype.creators.traypublisher.csv_ingest"

    default_variants = ["Main"]

    description = "Ingest products' data from CSV file"
    detailed_description = """
Ingest products' data from CSV file following column and representation
configuration in project settings.
"""

    # Position batch creator after editorial creator
    order = 10

    def apply_settings(self, project_settings):
        creator_settings = (
            project_settings["traypublisher"]["create"]["IngestCSV"]
        )
        self.column_config = creator_settings["columns_config"]
        self.representation_config = creator_settings["representations_config"]

    def create(self, subset_name, instance_data, pre_create_data):
        """Create an product from each row found in the CSV.

        Args:
            subset_name (str): The subset name.
            instance_data (dict): The instance data.
            pre_create_data (dict):
        """
        csv_filepath_data = pre_create_data.get("csv_filepath_data", {})

        folder = csv_filepath_data.get("directory", "")
        if not os.path.exists(folder):
            raise FileNotFoundError(
                f"Directory '{folder}' does not exist."
            )
        filename = csv_filepath_data.get("filenames", [])
        self._process_csv_file(subset_name, instance_data, folder, filename[0])

    def _process_csv_file(
            self, subset_name, instance_data, staging_dir, filename):
        """Process CSV file.

        Args:
            subset_name (str): The subset name.
            instance_data (dict): The instance data.
            staging_dir (str): The staging directory.
            filename (str): The filename.
        """

        # create new instance from the csv editorial file via self function
        self._pass_data_to_csv_instance(
            instance_data,
            staging_dir,
            filename
        )

        csv_instance = CreatedInstance(
            self.family, subset_name, instance_data, self
        )
        self._store_new_instance(csv_instance)

        csv_instance["csvFileData"] = {
            "filename": filename,
            "staging_dir": staging_dir,
        }

        # from special function get all data from csv file and convert them
        # to new instances
        csv_data_for_instances = self._get_data_from_csv(
            staging_dir, filename)

        # create instances from csv data via self function
        self._create_instances_from_csv_data(
            csv_data_for_instances, staging_dir
        )

    def _create_instances_from_csv_data(
        self,
        csv_data_for_instances,
        staging_dir
    ):
        """Create instances from csv data"""

        for asset_name, _data in csv_data_for_instances.items():
            asset_doc = _data["asset_doc"]
            vendor_name = _data["vendor_name"]
            products = _data["products"]

            for instance_name, product_data in products.items():
                # get important instance variables
                task_name = product_data["task_name"]
                variant_name = product_data["variant_name"]
                product_type = product_data["product_type"]
                version = product_data["version"]

                # create subset/product name
                product_name = get_subset_name(
                    product_type,
                    variant_name,
                    task_name,
                    asset_doc,
                )

                # make sure frame start/end is inherited from csv columns
                # if they exists or inherit them from asset doc for case where
                # columns are missing because only mov or mp4 files needs to be
                # published
                frame_start = None
                frame_end = None
                handle_start = None
                handle_end = None
                comment = None
                intent = None
                is_calculated = False
                for filepath, repre_data in product_data["representations"].items():  # noqa: E501
                    if not comment and repre_data["notes"]:
                        comment = repre_data["notes"]
                    if not intent and repre_data["intent"]:
                        intent = repre_data["intent"]
                        if intent:
                            comment = f"{intent}: {comment}"

                    extension = os.path.splitext(filepath)[-1]
                    # INFO: mp4 representation doesn't have to have frameStart
                    # and frameEnd columns
                    if extension in [".mp4"]:
                        continue

                    if (
                        frame_start is None
                        and repre_data["frameStart"] is not None
                    ):
                        frame_start = repre_data["frameStart"]
                    if (
                        frame_end is None
                        and repre_data["frameEnd"] is not None
                    ):
                        frame_end = repre_data["frameEnd"]
                    if (
                        handle_start is None
                        and repre_data["handleStart"] is not None
                    ):
                        handle_start = repre_data["handleStart"]
                    if (
                        handle_end is None
                        and repre_data["handleEnd"] is not None
                    ):
                        handle_end = repre_data["handleEnd"]

                    # recalculating framerange since handles are included in
                    # frameStart and frameEnd and also slate is included too
                    # INFO: handles are expected to be included so they
                    #   are taken out from frameStart and frameEnd
                    if frame_start and frame_end and not is_calculated:
                        # exclude handle only if any
                        if handle_start is not None:
                            frame_start = frame_start + handle_start
                        # also include slate frame if slate is True
                        if repre_data["slate"]:
                            frame_start = frame_start + 1
                        # exclude handle only if any
                        if handle_end is not None:
                            frame_end = frame_end - handle_end

                        is_calculated = True

                # for cases where no frame start and end columns are present
                if not frame_start:
                    frame_start = asset_doc["data"]["frameStart"]
                if not frame_end:
                    frame_end = asset_doc["data"]["frameEnd"]
                if handle_start is None:
                    handle_start = asset_doc["data"]["handleStart"]
                if handle_end is None:
                    handle_end = asset_doc["data"]["handleEnd"]

                # get representations from product data
                representations = product_data["representations"]
                label = f"{asset_name}_{product_name}_v{version:>03}"

                # make product data
                product_data = {
                    "name": instance_name,
                    "asset": asset_name,
                    "families": ["csv"],
                    "label": label,
                    "task": task_name,
                    "variant": variant_name,
                    "source": "csv",
                    "user": vendor_name,
                    "frameStart": frame_start,
                    "frameEnd": frame_end,
                    "handleStart": handle_start,
                    "handleEnd": handle_end,
                    "version": version,
                    "comment": comment,
                }

                # create new instance
                new_instance = CreatedInstance(
                    product_type, product_name, product_data, self
                )
                self._store_new_instance(new_instance)

                if not new_instance.get("prepared_data_for_repres"):
                    new_instance["prepared_data_for_repres"] = []

                base_thumbnail_repre_data = {
                    "name": "thumbnail",
                    "ext": None,
                    "files": None,
                    "stagingDir": None,
                    "stagingDir_persistent": True,
                    "tags": ["thumbnail", "delete"],
                }
                # need to populate all thumbnails for all representations
                # so we can check if unique thumbnail per representation
                # is needed
                thumbnails = [
                    repre_data["thumbnailPath"]
                    for repre_data in representations.values()
                    if repre_data["thumbnailPath"]
                ]
                multiple_thumbnails = len(set(thumbnails)) > 1
                explicit_output_name = None
                thumbnails_processed = False
                for filepath, repre_data in representations.items():
                    # check if any review derivate tag is present
                    reviewable = any(
                        tag for tag in repre_data.get("tags", [])
                        # tag can be `ftrackreview` or `review`
                        if "review" in tag
                    )
                    # since we need to populate multiple thumbnails as
                    # representation with outputName for ftrack instance
                    # integrator is able to pair them with reviewable
                    # representations
                    if (
                        thumbnails
                        and multiple_thumbnails
                        and reviewable
                    ):
                        # multiple unique thumbnails per representation
                        explicit_output_name = repre_data["output"]
                        relative_thumbnail_path = repre_data["thumbnailPath"]
                        # representation might not have thumbnail path
                        # so ignore this one
                        if not relative_thumbnail_path:
                            continue
                        thumb_dir, thumb_file = \
                            self._get_refactor_thumbnail_path(
                                staging_dir, relative_thumbnail_path)
                        filename, ext = os.path.splitext(thumb_file)
                        thumbnail_repr_data = deepcopy(
                            base_thumbnail_repre_data)
                        thumbnail_repr_data.update({
                            "name": "thumbnail_{}".format(filename),
                            "ext": ext[1:],
                            "files": thumb_file,
                            "stagingDir": thumb_dir,
                            "outputName": explicit_output_name,
                        })
                        new_instance["prepared_data_for_repres"].append(
                            ("_thumbnail_", thumbnail_repr_data)
                        )
                    elif (
                        thumbnails
                        and not multiple_thumbnails
                        and not thumbnails_processed
                        or not reviewable
                    ):
                        # here we will use only one thumbnail for
                        # all representations
                        relative_thumbnail_path = repre_data["thumbnailPath"]
                        if not relative_thumbnail_path:
                            relative_thumbnail_path = thumbnails.pop()
                        thumb_dir, thumb_file = \
                            self._get_refactor_thumbnail_path(
                                staging_dir, relative_thumbnail_path)
                        _, ext = os.path.splitext(thumb_file)
                        thumbnail_repr_data = deepcopy(
                            base_thumbnail_repre_data)
                        thumbnail_repr_data.update({
                            "ext": ext[1:],
                            "files": thumb_file,
                            "stagingDir": thumb_dir
                        })
                        new_instance["prepared_data_for_repres"].append(
                            ("_thumbnail_", thumbnail_repr_data)
                        )
                        thumbnails_processed = True

                    # get representation data
                    representation_data = self._get_representation_data(
                        filepath, repre_data, staging_dir,
                        explicit_output_name=explicit_output_name
                    )

                    new_instance["prepared_data_for_repres"].append(
                        (repre_data["color"], representation_data)
                    )

    def _get_refactor_thumbnail_path(
            self, staging_dir, relative_thumbnail_path):
        thumbnail_abs_path = os.path.join(
            staging_dir, relative_thumbnail_path)
        return os.path.split(
            thumbnail_abs_path)

    def _get_representation_data(
        self, filepath, repre_data, staging_dir, explicit_output_name=None
    ):
        """Get representation data"""

        # get extension of file
        basename = os.path.basename(filepath)
        _, extension = os.path.splitext(filepath)

        # validate filepath is having correct extension based on output
        config_repre_data = self.representation_config["representations"]
        output = repre_data["output"]
        if output not in config_repre_data:
            raise KeyError(
                f"Output '{output}' not found in config representation data."
            )
        validate_extensions = config_repre_data[output]["extensions"]
        if extension not in validate_extensions:
            raise TypeError(
                f"File extension '{extension}' not valid for "
                f"output '{validate_extensions}'."
            )

        is_sequence = (extension in IMAGE_EXTENSIONS)
        # convert ### string in file name to %03d
        # this is for correct frame range validation
        # example: file.###.exr -> file.%03d.exr
        if "#" in basename:
            padding = len(basename.split("#")) - 1
            basename = basename.replace("#" * padding, f"%0{padding}d")
            is_sequence = True

        # make absolute path to file
        absfilepath = os.path.normpath(os.path.join(staging_dir, filepath))
        dirname = os.path.dirname(absfilepath)

        # check if dirname exists
        if not os.path.isdir(dirname):
            raise NotADirectoryError(
                f"Directory '{dirname}' does not exist."
            )

        # collect all data from dirname
        paths_for_collection = []
        for file in os.listdir(dirname):
            filepath = os.path.join(dirname, file)
            paths_for_collection.append(filepath)

        collections, _ = clique.assemble(paths_for_collection)

        if collections:
            collections = collections[0]
        else:
            if is_sequence:
                raise ValueError(
                    f"No collections found in directory '{dirname}'."
                )

        frame_start = None
        frame_end = None
        if is_sequence:
            files = [os.path.basename(file) for file in collections]
            frame_start = list(collections.indexes)[0]
            frame_end = list(collections.indexes)[-1]
        else:
            files = basename

        tags = deepcopy(repre_data["tags"])
        # if slate in repre_data is True then remove one frame from start
        if repre_data["slate"]:
            tags.append("has_slate")

        # get representation data
        representation_data = {
            "name": output,
            "ext": extension[1:],
            "files": files,
            "stagingDir": dirname,
            "stagingDir_persistent": True,
            "tags": tags,
        }
        if extension in VIDEO_EXTENSIONS:
            representation_data.update({
                "fps": 25,
                "outputName": output,
            })

        if explicit_output_name:
            representation_data["outputName"] = explicit_output_name

        if frame_start:
            representation_data["frameStart"] = frame_start
        if frame_end:
            representation_data["frameEnd"] = frame_end

        return representation_data

    def _get_data_from_csv(
        self, package_dir, filename
    ):
        """Generate instances from the csv editorial file"""
        # get current project name and code from context.data
        project_name = self.create_context.get_current_project_name()
        current_username = get_openpype_username()

        csv_file_path = os.path.join(
            package_dir, filename
        )

        # make sure csv file contains columns from following list
        required_columns = [
            name for name, value in self.column_config["columns"].items()
            if value["required"]
        ]
        # get data from csv file
        with open(csv_file_path, "r") as csv_file:
            csv_reader = csv.DictReader(
                csv_file, delimiter=self.column_config["csv_delimiter"])

            # fix fieldnames
            # sometimes someone can keep extra space at the start or end of
            # the column name
            all_columns = [
                " ".join(column.rsplit()) for column in csv_reader.fieldnames]
            # return back fixed fieldnames
            csv_reader.fieldnames = all_columns

            # check if csv file contains all required columns
            if any(column not in all_columns for column in required_columns):
                raise KeyError(
                    f"Missing required columns: {required_columns}"
                )

            csv_data = {}
            # get data from csv file
            for row in csv_reader:
                # get project from row or get default current project
                row_project_name = self._get_row_value_with_validation(
                    "Project", row, default_value=project_name
                )

                # raise if row project name is not equal to current
                # project name
                if row_project_name != project_name:
                    raise ValueError(
                        f"Project name in csv file '{row_project_name}' "
                        "must be equal to current project name: "
                        f"{project_name}"
                    )
                # get Package row value
                package = self._get_row_value_with_validation(
                    "Package", row, default_value=package_dir)

                if (package and package != os.path.basename(package_dir)):
                    raise ValueError(
                        f"Package name in csv file '{package}' "
                        "must be equal to package folder name: "
                        f"{package_dir}"
                    )

                row_vendor_name = self._get_row_value_with_validation(
                    "Vendor", row, default_value=current_username
                )

                # get related shot asset
                context_asset_name = self._get_row_value_with_validation(
                    "Context", row)

                # get Task row value
                task_name = self._get_row_value_with_validation(
                    "Task", row)

                # get Variant row value
                variant_name = self._get_row_value_with_validation(
                    "Variant", row)

                # get Family row value
                product_type = self._get_row_value_with_validation(
                    "Family", row)

                # get Version row value
                version = self._get_row_value_with_validation(
                    "Version", row)

                pre_product_name = (
                    f"{task_name}{variant_name}{product_type}"
                    f"{version}".replace(" ", "").lower()
                )

                # get representation data
                filename, representation_data = \
                    self._get_representation_row_data(row)

                # get all csv data into one dict and make sure there are no
                # duplicates data are already validated and sorted under
                # correct existing asset also check if asset exists and if
                # task name is valid task in asset doc and representations
                # are distributed under products following variants
                if context_asset_name not in csv_data:
                    asset_doc = get_asset_by_name(
                        project_name, context_asset_name)

                    # make sure asset exists
                    if not asset_doc:
                        raise ValueError(
                            f"Asset '{context_asset_name}' not found."
                        )
                    # check if task name is valid task in asset doc
                    if task_name not in asset_doc["data"]["tasks"]:
                        raise ValueError(
                            f"Task '{task_name}' not found in asset doc."
                        )

                    csv_data[context_asset_name] = {
                        "asset_doc": asset_doc,
                        "vendor_name": row_vendor_name,
                        "products": {
                            pre_product_name: {
                                "task_name": task_name,
                                "variant_name": variant_name,
                                "product_type": product_type,
                                "version": version,
                                "representations": {
                                    filename: representation_data,
                                },
                            }
                        }
                    }
                else:
                    asset_doc = csv_data[context_asset_name]["asset_doc"]
                    csv_products = csv_data[context_asset_name]["products"]
                    if pre_product_name not in csv_products:
                        csv_products[pre_product_name] = {
                            "task_name": task_name,
                            "variant_name": variant_name,
                            "product_type": product_type,
                            "version": version,
                            "representations": {
                                filename: representation_data,
                            },
                        }
                    else:
                        csv_representations = \
                            csv_products[pre_product_name]["representations"]
                        if filename in csv_representations:
                            raise ValueError(
                                f"Duplicate filename '{filename}' in csv file."
                            )
                        csv_representations[filename] = representation_data

        return csv_data

    def _get_representation_row_data(self, row_data):
        """Get representation row data"""
        # get Filename row value
        filename = self._get_row_value_with_validation(
            "Filename", row_data)
        thumbnail_path = self._get_row_value_with_validation(
            "Thumbnail", row_data)
        # get Version row value
        version = self._get_row_value_with_validation(
            "Version", row_data)
        # get Color row value
        color = self._get_row_value_with_validation(
            "Color", row_data)
        # get Notes row value
        notes = self._get_row_value_with_validation(
            "Notes", row_data)
        # get Intent row value
        intent = self._get_row_value_with_validation(
            "Intent", row_data)
        # get Output row value
        output = self._get_row_value_with_validation(
            "Output", row_data)
        # get Slate row value
        slate = self._get_row_value_with_validation(
            "Slate", row_data)
        # get Tag row value
        tags = self._get_row_value_with_validation(
            "Tags", row_data)

        # convert tags value to list
        tags_list = copy(self.representation_config["default_tags"])
        if tags:
            tags_list = []
            tags_delimiter = self.representation_config["tags_delimiter"]
            # strip spaces from tags
            if tags_delimiter in tags:
                tags = tags.split(tags_delimiter)
                for _tag in tags:
                    tags_list.append(("".join(_tag.strip())).lower())
            else:
                tags_list.append(("".join(tags.strip())).lower())

        # get Start row value
        frame_start = self._get_row_value_with_validation(
            "Start", row_data)
        # get End row value
        frame_end = self._get_row_value_with_validation(
            "End", row_data)

        # get Head row value
        handle_start = self._get_row_value_with_validation(
            "Head", row_data)

        # get Tail row value
        handle_end = self._get_row_value_with_validation(
            "Tail", row_data)

        frame_length = self._get_row_value_with_validation(
            "Length", row_data)

        representation_data = {
            "version": int(version),
            "color": color,
            "notes": notes,
            "intent": intent,
            "output": output,
            "slate": slate,
            "tags": tags_list,
            "thumbnailPath": thumbnail_path,
            "frameStart": (
                int(frame_start) if frame_start is not None else None),
            "frameEnd": (
                int(frame_end) if frame_end is not None else None),
            "handleStart": (
                int(handle_start) if handle_start is not None else None),
            "handleEnd": (
                int(handle_end) if handle_end is not None else None),
            "frameLength": int(frame_length) if frame_length else None
        }

        return filename, representation_data

    def _get_row_value_with_validation(
        self, column_name, row_data, default_value=None
    ):
        """Get row value with validation"""
        column_config = self.column_config["columns"]
        # get column data from column config
        column_data = column_config.get(column_name)
        if not column_data:
            raise KeyError(
                f"Column '{column_name}' not found in column config."
            )

        # get column value from row
        column_value = row_data.get(column_name)
        # get column type
        column_type = column_data["type"]
        # get column validation regex
        column_validation = column_data["validate"]
        # get column default value
        column_default = default_value or column_data["default"]

        if column_type == "number" and column_default == 0:
            column_default = None

        # check if column value is not empty string
        if column_value == "":
            # set default value if column value is empty string
            column_value = column_default

        # set column value to correct type following column type
        if column_type == "number" and column_value is not None:
            column_value = int(column_value)
        elif column_type == "bool":
            column_value = column_value in ["true", "True"]

        # check if column value matches validation regex
        if (
            column_value is not None and
            not re.match(str(column_validation), str(column_value))
        ):
            raise ValueError(
                f"Column '{column_name}' value '{column_value}' "
                f"does not match validation regex '{column_validation}' \n"
                f"Row data: {row_data} \n"
                f"Column data: {column_data}"
            )

        return column_value

    def _pass_data_to_csv_instance(
        self, instance_data, staging_dir, filename
    ):
        """Pass CSV representation file to instance data"""

        representation = {
            "name": "csv",
            "ext": "csv",
            "files": filename,
            "stagingDir": staging_dir,
            "stagingDir_persistent": True,
        }

        instance_data.update({
            "label": f"CSV: {filename}",
            "representations": [representation],
            "stagingDir": staging_dir,
            "stagingDir_persistent": True,
        })

    def get_instance_attr_defs(self):
        return [
            BoolDef(
                "add_review_family",
                default=True,
                label="Review"
            )
        ]

    def get_pre_create_attr_defs(self):
        """Creating pre-create attributes at creator plugin.

        Returns:
            list: list of attribute object instances
        """
        # Use same attributes as for instance attrobites
        attr_defs = [
            FileDef(
                "csv_filepath_data",
                folders=False,
                extensions=[".csv"],
                allow_sequences=False,
                single_item=True,
                label="CSV File",
            ),
        ]
        return attr_defs
