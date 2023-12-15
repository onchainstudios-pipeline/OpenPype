from openpype.pipeline import install_host
from openpype.hosts.nuke.api import NukeHost
from hornet_deadline_utils import deadlineNetworkSubmit
host = NukeHost()
install_host(host)

# TODO horent:old heck with output format, see hornet commit 153ccd9
import nuke
import os

import DeadlineNukeClient

from openpype.lib import Logger
from openpype.hosts.nuke import api
from openpype.hosts.nuke.api.lib import (
    on_script_load,
    check_inventory_versions,
    WorkfileSettings,
    dirmap_file_name_filter,
    add_scripts_gizmo
)
from openpype.settings import get_project_settings

log = Logger.get_logger(__name__)
# dict mapping extension to list of exposed parameters from write node to top level group node
knobMatrix = { 'exr': ['autocrop', 'datatype', 'heroview', 'metadata', 'interleave'],
                'png': ['datatype'],
                'dpx': ['datatype'],
                'tiff': ['datatype', 'compression'],
                'jpeg': []
}
universalKnobs = ['colorspace', 'views','first', 'last','use_limit']

knobMatrix = {key: universalKnobs + value for key, value in knobMatrix.items()}
#list of key-value tuples for write node knob presets based on file extension
presets = {
    'exr' : [ ("colorspace", 'ACES - ACEScg'), ('channels', 'all'), ('datatype', '16 bit half') ],
    'png' : [ ("colorspace", 'Output - Rec.709'), ('channels', 'rgba'), ('datatype','16 bit') ],
    'dpx' : [ ("colorspace", 'Output - Rec.709'), ('channels', 'rgb'), ('datatype','10 bit'), ('big endian', True) ],
    'jpeg' : [ ("colorspace", 'Output - sRGB'), ('channels', 'rgb') ]
           }
# fix ffmpeg settings on script

# set checker for last versions on loaded containers

log.info('Automatic syncing of write file knob to script version')


def apply_format_presets():
    node = nuke.thisNode()
    knob = nuke.thisKnob()
    if knob.name() == 'file_type':
        if knob.value() in presets.keys():
            for preset in presets[knob.value()]:
                if node.knob(preset[0]):
                    node.knob(preset[0]).setValue(preset[1])
# Hornet- helper to switch file extension to filetype
def writes_ver_sync():
    ''' Callback synchronizing version of publishable write nodes
    '''
    try:
        print('Hornet- syncing version to write nodes')
        #rootVersion = pype.get_version_from_path(nuke.root().name())
        pattern = re.compile(r"[\._]v([0-9]+)", re.IGNORECASE)
        rootVersion = pattern.findall(nuke.root().name())[0]
        padding = len(rootVersion)
        new_version = "v" + str("{" + ":0>{}".format(padding) + "}").format(
            int(rootVersion)
        )
        print("new_version: {}".format(new_version))
    except Exception as e:
        print(e)
        return
    groupnodes = [node.nodes() for node in nuke.allNodes() if node.Class() == 'Group']
    allnodes = [node for group in groupnodes for node in group] + nuke.allNodes()
    for each in allnodes:
        if each.Class() == 'Write':
            # check if the node is avalon tracked
            if each.name().startswith('inside_'):
                avalonNode = nuke.toNode(each.name().replace('inside_',''))
            else:
                avalonNode = each
            if "AvalonTab" not in avalonNode.knobs():
                print("tab failure")
                continue

            avalon_knob_data = avalon.nuke.get_avalon_knob_data(
                avalonNode, ['avalon:', 'ak:'])
            try:
                if avalon_knob_data['families'] not in ["render", "write"]:
                    print("families fail")
                    log.debug(avalon_knob_data['families'])
                    continue

                node_file = each['file'].value()

                #node_version = "v" + pype.get_version_from_path(node_file)
                node_version = 'v' + pattern.findall(node_file)[0]

                log.debug("node_version: {}".format(node_version))

                node_new_file = node_file.replace(node_version, new_version)
                each['file'].setValue(node_new_file)
                #H: don't need empty folders if work file isn't rendered later
                #if not os.path.isdir(os.path.dirname(node_new_file)):
                #    log.warning("Path does not exist! I am creating it.")
                #    os.makedirs(os.path.dirname(node_new_file), 0o766)
            except Exception as e:
                print(e)
                log.warning(
                    "Write node: `{}` has no version in path: {}".format(
                        each.name(), e))


def switchExtension():
    nde = nuke.thisNode()
    knb = nuke.thisKnob()
    if knb == nde.knob('file_type'):
        filek = nde.knob('file')
        old = filek.value()
        pre,ext = os.path.splitext(old)
        filek.setValue(pre + '.' + knb.value())

def embedOptions():
    nde = nuke.thisNode()
    knb = nuke.thisKnob()
    log.info(' knob of type' + str(knb.Class()))
    htab = nuke.Tab_Knob('htab','Hornet')
    htab.setName('htab')
    if knb == nde.knob('file_type'):
        group = nuke.toNode('.'.join(['root'] + nde.fullName().split('.')[:-1]))
        ftype = knb.value()
    else:
        return
    if ftype not in knobMatrix.keys():
        return
    allTrackedKnobs = [ value for sublist in knobMatrix.values() for value in sublist]
    for kname in ['file_type','file','channels','Render Local']:
        allTrackedKnobs.append(kname)
    allLinkedKnobs = [knob for knob in group.allKnobs() if isinstance(knob, nuke.Link_Knob)]
    allTabKnobs = [knob for knob in group.allKnobs() if isinstance(knob, nuke.Tab_Knob)]
    allTextKnobs = [knob for knob in group.allKnobs() if isinstance(knob, nuke.Text_Knob) or isinstance(knob, nuke.String_Knob) or isinstance(knob, nuke.Int_Knob)]
    allScriptKnobs = [knob for knob in group.allKnobs() if isinstance(knob, nuke.PyScript_Knob)]
    allMultiKnobs = [knob for knob in group.allKnobs() if isinstance(knob, nuke.Multiline_Eval_String_Knob)]
    for knob in allLinkedKnobs:
        if knob.name() in allTrackedKnobs:
            group.removeKnob(knob)
    for knob in allTabKnobs:
        if knob.name() in ['beginoutput','endoutput','beginpipeline','beginoutput','endpipeline','htab']:
            group.removeKnob(knob)
    for knob in allScriptKnobs:
        if knob.name() in ["submit","publish", "readfrom", 'clear']:
            group.removeKnob(knob)
    for knob in allMultiKnobs:
        if knob.name() == "File output":
            group.removeKnob(knob)
    for knob in allTextKnobs:
        if knob.name() in ['tempwarn','reviewwarn','dlinewarn','div','deadlinediv', 'deadlinePriority', 'deadlineGroup', 'deadlinePool', 'deadlineChunkSize']:
            group.removeKnob(knob)
    names = [knob.name() for knob in group.allKnobs()]
    if not 'htab' in names:
        group.addKnob(htab)
    beginGroup = nuke.Tab_Knob('beginoutput', 'Output', nuke.TABBEGINGROUP)
    group.addKnob(beginGroup)

    if 'file' not in group.knobs().keys():
        fle = nuke.Multiline_Eval_String_Knob('File output')
        fle.setText(nde.knob('file').value())
        group.addKnob(fle)
        link = nuke.Link_Knob('channels')
        link.makeLink(nde.name(), 'channels')
        link.setName('channels')
        group.addKnob(link)
        if 'file_type' not in group.knobs().keys():
            link = nuke.Link_Knob('file_type')
            link.makeLink(nde.name(), 'file_type')
            link.setName('file_type')
            link.setFlag(0x1000)
            group.addKnob(link)
        for kname in knobMatrix[ftype]:
            link = nuke.Link_Knob(kname)
            link.makeLink(nde.name(), kname)
            link.setName(kname)
            link.setFlag(0x1000)
            if kname in ['first','last']:
                link.setLabel(kname + ' frame')
            if kname == 'use_limit':
                link.setLabel('use frame range')
            group.addKnob(link)
    log.info("links made")
    if group.knob('first').value() == 1:
        group.knob('first').setValue(nuke.root().firstFrame())
    if group.knob('last').value() == 1:
        group.knob('last').setValue(nuke.root().lastFrame())

    endGroup = nuke.Tab_Knob('endoutput', None, nuke.TABENDGROUP)
    group.addKnob(endGroup)
    beginGroup = nuke.Tab_Knob('beginpipeline', 'Rendering and Pipeline', nuke.TABBEGINGROUP)
    group.addKnob(beginGroup)
    sub = nuke.PyScript_Knob('submit', 'Submit to Deadline', "deadlineNetworkSubmit()")
    sub.setFlag(0x00001000)
    clr = nuke.PyScript_Knob('clear', 'Clear Temp Outputs', "import os;fpath = os.path.dirname(nuke.thisNode().knob('File output').value());[os.remove(os.path.join(fpath, f)) for f in os.listdir(fpath)]")
    pub = nuke.PyScript_Knob('publish', 'Publish', "from openpype.tools.utils import host_tools;host_tools.show_publisher(parent=(main_window if nuke.NUKE_VERSION_MAJOR >= 14 else None),tab='Publish')")
    readfrom_src = "import write_to_read;write_to_read.write_to_read(nuke.thisNode(), allow_relative=False)"
    readfrom = nuke.PyScript_Knob('readfrom', 'Read From Rendered', readfrom_src)
    link = nuke.Link_Knob('render')
    link.makeLink(nde.name(), 'Render')
    link.setName('Render Local')
    group.addKnob(link)

    div = nuke.Text_Knob('div','','')
    deadlinediv = nuke.Text_Knob('deadlinediv','Deadline','')
    deadlinePriority = nuke.Int_Knob('deadlinePriority', 'Priority')
    deadlinePool = nuke.String_Knob('deadlinePool', 'Pool')
    deadlineGroup = nuke.String_Knob('deadlineGroup', 'Group')
    deadlineChunkSize = nuke.Int_Knob('deadlineChunkSize', 'Chunk Size')
    deadlineChunkSize.setValue(1)
    deadlinePool.setValue('local')
    deadlineGroup.setValue('nuke')
    deadlinePriority.setValue(90)

    group.addKnob(readfrom)
    group.addKnob(clr)
    group.addKnob(deadlinediv)
    group.addKnob(deadlinePriority)
    group.addKnob(deadlineChunkSize)
    group.addKnob(deadlinePool)
    group.addKnob(deadlineGroup)
    group.addKnob(sub)
    group.addKnob(div)
    group.addKnob(pub)
    tempwarn = nuke.Text_Knob('tempwarn', '', '- all rendered files are TEMPORARY and WILL BE OVERWRITTEN unless published ')
    group.addKnob(tempwarn)



    endGroup = nuke.Tab_Knob('endpipeline', None, nuke.TABENDGROUP)
    group.addKnob(endGroup)

def enable_disable_frame_range():
    nde = nuke.thisNode()
    knb = nuke.thisKnob()
    if not nde.knob('use_limit') or not knb.name() == 'use_limit':
        return
    group = nuke.toNode('.'.join(['root'] + nde.fullName().split('.')[:-1]))
    enable = nde.knob('use_limit').value()
    group.knobs()['first'].setEnabled(enable)
    group.knobs()['last'].setEnabled(enable)

def submit_selected_write():
    for nde in nuke.selectedNodes():
        if nde.Class() == 'Write':
            submit_write(nde)

nuke.addKnobChanged(switchExtension, nodeClass='Write')
nuke.addKnobChanged(embedOptions, nodeClass='Write')
nuke.addKnobChanged(apply_format_presets, nodeClass='Write')
nuke.addKnobChanged(enable_disable_frame_range, nodeClass='Write')
nuke.addOnScriptSave(writes_ver_sync)
