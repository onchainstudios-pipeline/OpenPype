
import click

# from openpype.lib import get_openpype_execute_args
# from openpype.lib.execute import run_detached_process
from openpype.modules import OpenPypeModule, ITrayAction, IHostAddon


class BatchPublishAddon(OpenPypeModule, IHostAddon, ITrayAction):
    label = "Batch Publisher"
    name = "batchpublisher"
    host_name = "batchpublisher"

    def initialize(self, modules_settings):
        self.enabled = True
        # UI which must not be created at this time
        self._dialog = None

    def tray_init(self):
        return

    def on_action_trigger(self):
        self.show_dialog()
        # self.run_batchpublisher()

    def connect_with_modules(self, enabled_modules):
        """Collect publish paths from other modules."""
        return

    # def run_batchpublisher(self):
    #     name = "traypublisher"
    #     args = get_openpype_execute_args(
    #         "module", name, "launch"
    #         # "module", self.name, "launch"
    #     )
    #     print("ARGS" , args)
    #     run_detached_process(args)

    def cli(self, click_group):
        click_group.add_command(cli_main)

    def _create_dialog(self):
        # # Don't recreate dialog if already exists
        # if self._dialog is not None:
        #     return

        import importlib
        import openpype.hosts.batchpublisher.widgets
        importlib.reload(openpype.hosts.batchpublisher.widgets)

        # from openpype.hosts.batchpublisher.widgets \
        #     import BatchPublisherWindow
        self._dialog = openpype.hosts.batchpublisher \
            .widgets.BatchPublisherWindow()

    def show_dialog(self):
        """Show dialog with connected modules.

        This can be called from anywhere but can also crash in headless mode.
        There is no way to prevent addon to do invalid operations if he's
        not handling them.
        """
        # Make sure dialog is created
        self._create_dialog()
        # Show dialog
        self._dialog.show()


@click.group(BatchPublishAddon.name, help="BatchPublisher related commands.")
def cli_main():
    pass


@cli_main.command()
def launch():
    """Launch BatchPublisher tool UI."""
    print("LAUNCHING BATCH PUBLISHER")
    from openpype.tools import batchpublisher
    batchpublisher.main()