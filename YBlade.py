#Author-Jan Mrázek, Updated by sophusand (2025)
#Description-Import QBlade wind turbine blade designs into Fusion 360. Supports QBlade v0.963 and CE v2.x formats.

import adsk.core, adsk.fusion, adsk.cam, traceback
from adsk.core import Point3D, Vector3D, Matrix3D
import math
import sys 
import os

handlers = []
sys.stderr = sys.stdout
sys.stdout.flush()

profile_cache = {}


def append_status(inputs, message):
    status_box = inputs.itemById('statusLog')
    if not status_box:
        return
    current = status_box.text.strip()
    status_box.text = (current + '\n' + message).strip() if current else message


def open_file_dialog(ui, title, file_filter='*.*'):
    file_dlg = ui.createFileDialog()
    file_dlg.isMultiSelectEnabled = False
    file_dlg.title = title
    file_dlg.filter = file_filter
    if file_dlg.showOpen() == adsk.core.DialogResults.DialogOK:
        return file_dlg.filenames[0]
    return None


def loadProfile(profilePath):
    cached = profile_cache.get(profilePath)
    if cached:
        return cached

    points = []
    try:
        with open(profilePath, 'r') as profileFile:
            for l in profileFile.readlines()[1:]:
                tokens = l.split()
                if len(tokens) < 2:
                    continue
                try:
                    points.append((float(tokens[0]), float(tokens[1])))
                except ValueError:
                    continue
    except OSError as err:
        raise RuntimeError(f'Failed to read airfoil file: {err}')

    if not points:
        raise RuntimeError('Airfoil file contained no coordinate data.')

    profile_cache[profilePath] = points
    return points

class Struct(object): pass

def readBlade(bladeFile):
    sections = []
    lines = bladeFile.readlines()
    
    # Detect file format
    isNewFormat = False
    dataStartLine = 3  # Default for old format
    
    for i, line in enumerate(lines):
        if "Blade Data" in line:
            isNewFormat = True
            # Skip past the header line with "POS_[m]"
            for j in range(i + 1, len(lines)):
                if "POS_[m]" in lines[j]:
                    dataStartLine = j + 1  # Start after the header
                    break
            break
    
    # Parse based on format
    profileCounts = {}  # Track which profile is used most
    mainProfile = None  # The profile we'll use (most common non-circular)
    
    for l in lines[dataStartLine:]:
        stripped = l.strip()
        if not stripped or stripped.startswith("-"):
            continue
            
        x = stripped.split()
        if len(x) < 5:
            continue
            
        try:
            s = Struct()
            s.pos = float(x[0]) * 100  # Convert to cm
            s.len = float(x[1]) * 100  # Convert to cm 
            s.twist = float(x[2])
            
            if isNewFormat:
                # New format: POS CHORD TWIST OFFSET_X OFFSET_Y P_AXIS POLAR_FILE
                # OFFSET_Y is used as offset
                s.offset = float(x[4]) * 100  # Convert to cm
                s.thread = float(x[5])
                
                # Track profile usage
                if len(x) > 6:
                    profile = x[6]
                    # Skip circular profiles - we want the main airfoil
                    if "Circular" not in profile and "circular" not in profile:
                        profileCounts[profile] = profileCounts.get(profile, 0) + 1
                    s.profile = profile
            else:
                # Old format: POS CHORD TWIST OFFSET THREAD
                s.offset = float(x[3]) * 100  # Convert to cm
                s.thread = float(x[4])
                s.profile = "default"
            
            sections.append(s)
        except (ValueError, IndexError):
            continue
    
    # Determine main profile (most common non-circular)
    if profileCounts:
        mainProfile = max(profileCounts, key=profileCounts.get)
    
    # Filter out sections that don't use the main profile
    if mainProfile:
        sections = [s for s in sections if hasattr(s, 'profile') and 
                   (s.profile == mainProfile or "Circular" not in s.profile)]
    
    return sections

def findClosest(target, l):
    """
    Find value in l closest target. Return index of such a value
    """
    minVal = l[0]
    minIdx = 0
    for i, e in enumerate(l):
        if abs(target - minVal) > abs(target - e):
            minVal = e
            minIdx = i
    return minIdx

def deduceOffset(blade, profile):
    positives = list([(x, y) for x, y in profile if y > 0])
    posIdx = findClosest(blade[0].thread, [x for x, y in positives])
    negatives = list([(x, y) for x, y in profile if y < 0])
    negIdx = findClosest(blade[0].thread, [x for x, y in negatives])

    mid = (positives[posIdx][1] + negatives[negIdx][1]) / 2

    for b in blade:
        b.offset = -mid * b.len

def profilePoints(profileData, chordLength, twist, threadAxisOffset, zoffset):
    pointSet = adsk.core.ObjectCollection.create()
    for profilePoint in profileData:
        p = Point3D.create(profilePoint[0] * chordLength, profilePoint[1] * chordLength, 0)
        p.translateBy(Vector3D.create(-chordLength * threadAxisOffset, zoffset))
        m = Matrix3D.create()
        m.setToRotation(math.radians(twist), Vector3D.create(0, 0, 1), Point3D.create(0, 0, 0))
        p.transformBy(m)
        pointSet.add(p)
    return pointSet

def drawProfile(sketch, profileData, chordLength, twist, threadAxisOffset, zoffset):
    pointSet = profilePoints(profileData, chordLength, twist, threadAxisOffset, zoffset)
    spline = sketch.sketchCurves.sketchFittedSplines.add(pointSet)
    first, last = pointSet.item(0), pointSet.item(pointSet.count - 1)
    line = sketch.sketchCurves.sketchLines.addByTwoPoints(first, last)
    profile = adsk.core.ObjectCollection.create()
    profile.add(spline)
    profile.add(line)
    return profile

def drawGuideLine(sketch, blade, seed):
    pointSet = adsk.core.ObjectCollection.create() 
    for s in blade:
        p = Point3D.create(seed[0] * s.len, seed[1] * s.len, s.pos)
        p.translateBy(Vector3D.create(-s.len * s.thread, s.offset))
        m = Matrix3D.create()
        m.setToRotation(math.radians(s.twist), Vector3D.create(0, 0, 1), Point3D.create(0, 0, 0))
        p.transformBy(m)
        pointSet.add(p)
    spline = sketch.sketchCurves.sketchFittedSplines.add(pointSet)
    return spline

def drawSpline(sketch, points):
    spline = sketch.sketchCurves.sketchFittedSplines.add(points)
    return adsk.fusion.Path.create(spline, adsk.fusion.ChainedCurveOptions.noChainedCurves)

def extrudeBlade(component, profiles, sweepLine, guideLine):
    if not profiles:
        raise RuntimeError('Cannot sweep blade without profile sketches.')

    sweepProfile = adsk.core.ObjectCollection.create()
    firstSketchProfiles = profiles[0].profiles
    if firstSketchProfiles.count == 0:
        raise RuntimeError('The first profile sketch contains no closed profiles.')

    # Always sweep the outer profile; include inner profile if present (legacy hollow design)
    sweepProfile.add(firstSketchProfiles.item(0))
    if firstSketchProfiles.count > 1:
        sweepProfile.add(firstSketchProfiles.item(1))

    path = component.features.createPath(sweepLine)
    guide = component.features.createPath(guideLine)

    sweeps = component.features.sweepFeatures
    sweepInput = sweeps.createInput(sweepProfile, path, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    sweepInput.guideRail = guide
    sweepInput.profileScaling = adsk.fusion.SweepProfileScalingOptions.SweepProfileScaleOption
    sweeps.add(sweepInput)

def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui  = app.userInterface
        commandDefinitions = ui.commandDefinitions

        design = app.activeProduct
        rootComp = design.activeComponent 

        defaultBladePath = ''
        defaultProfilePath = ''

        class YBladeExecuteHandler(adsk.core.CommandEventHandler):
            def __init__(self):
                super().__init__()
            def notify(self, args):
                try:
                    command = args.firingEvent.sender
                    inputs = command.commandInputs
                    profile_path = inputs.itemById('profilePath').value.strip()
                    blade_path = inputs.itemById('bladePath').value.strip()
                    remove_hub = inputs.itemById('removeHubRadius').value
                    center_mass = inputs.itemById('centerMass').value
                    append_status(inputs, 'Starting import...')

                    if not profile_path or not blade_path:
                        raise RuntimeError('Select both airfoil and blade files before running the import.')

                    progressDialog = ui.createProgressDialog()
                    progressDialog.cancelButtonText = 'Cancel'
                    progressDialog.isBackgroundTranslucent = False
                    progressDialog.isCancelButtonShown = False
                    progressDialog.show('QBlade Import', 'Reading files...', 0, 10)

                    sketches = rootComp.sketches
                    planes = rootComp.constructionPlanes
                    xyPlane = rootComp.xYConstructionPlane

                    profileData = loadProfile(profile_path)
                    append_status(inputs, f'Airfoil loaded ({len(profileData)} points).')

                    progressDialog.progressValue = 1
                    progressDialog.message = 'Processing blade sections...'

                    try:
                        with open(blade_path, 'r') as f:
                            blade = readBlade(f)
                    except OSError as err:
                        raise RuntimeError(f'Failed to read blade file: {err}')

                    append_status(inputs, f'Blade definition loaded ({len(blade)} sections).')
                    deduceOffset(blade, profileData)

                    if remove_hub:
                        hubOffset = min([b.pos for b in blade])
                        for b in blade:
                            b.pos -= hubOffset
                        append_status(inputs, f'Hub offset removed ({hubOffset:.2f} cm).')

                    progressDialog.progressValue = 2
                    progressDialog.message = f'Creating {len(blade)} blade profiles...'

                    timelineGroups = design.timeline.timelineGroups
                    groupStartIndex = design.timeline.markerPosition

                    profiles = []
                    prevLen = -1000
                    prevTwist = -1000
                    successfulBladeData = []

                    for i, b in enumerate(blade):
                        if abs(b.len - prevLen) < 1 and abs(b.twist - prevTwist) < 1 and i != len(blade) - 1:
                            continue
                        prevLen = b.len
                        prevTwist = b.twist

                        if len(profiles) % 5 == 0:
                            progress = 2 + int((i / max(1, len(blade))) * 5)
                            progressDialog.progressValue = progress
                            progressDialog.message = f'Creating profiles... {len(profiles)}/{len(blade)}'

                        planeInput = planes.createInput()
                        offsetValue = adsk.core.ValueInput.createByReal(b.pos)
                        planeInput.setByOffset(xyPlane, offsetValue)
                        plane = planes.add(planeInput)
                        plane.name = f"profile_{i}"
                        profileSketch = sketches.add(plane)
                        profileSketch.isLightBulbOn = False
                        drawProfile(profileSketch, profileData, b.len, b.twist, b.thread, b.offset)

                        profiles.append(profileSketch)
                        successfulBladeData.append(b)

                    if not profiles:
                        raise RuntimeError('No valid blade sections were generated. Check the QBlade and airfoil files.')
                    if len(successfulBladeData) < 2:
                        raise RuntimeError('At least two blade sections are required to build the blade.')

                    progressDialog.progressValue = 7
                    progressDialog.message = 'Building blade shell...'

                    guideSketch = sketches.add(xyPlane)
                    guideLine1 = drawGuideLine(guideSketch, successfulBladeData, (0, 0))
                    sweepLine = guideSketch.sketchCurves.sketchLines.addByTwoPoints(
                        Point3D.create(0, 0, blade[0].pos),
                        Point3D.create(0, 0, blade[-1].pos))

                    progressDialog.progressValue = 8
                    progressDialog.message = 'Building blade...'

                    bodyCountBefore = rootComp.bRepBodies.count

                    progressDialog.progressValue = 9
                    progressDialog.message = 'Finalizing blade...'

                    extrudeBlade(rootComp, profiles, sweepLine, guideLine1)

                    groupEndIndex = design.timeline.markerPosition - 1
                    if groupEndIndex >= groupStartIndex:
                        bladeGroup = timelineGroups.add(groupStartIndex, groupEndIndex)
                        bladeGroup.name = "QBlade Import"

                    allBodies = rootComp.bRepBodies
                    bodyCountAfter = allBodies.count
                    newBodies = []
                    if bodyCountAfter > bodyCountBefore:
                        for i in range(bodyCountBefore, bodyCountAfter):
                            newBodies.append(allBodies.item(i))

                    if center_mass and newBodies:
                        progressDialog.message = 'Centering blade by center of mass...'
                        totalMass = 0.0
                        weightedComX = 0.0
                        weightedComY = 0.0
                        minZ = float('inf')
                        for body in newBodies:
                            props = body.physicalProperties
                            mass = props.mass
                            com = props.centerOfMass
                            totalMass += mass
                            weightedComX += com.x * mass
                            weightedComY += com.y * mass
                            bbox = body.boundingBox
                            if bbox.minPoint.z < minZ:
                                minZ = bbox.minPoint.z

                        if totalMass > 0:
                            comX = weightedComX / totalMass
                            comY = weightedComY / totalMass
                            moveFeats = rootComp.features.moveFeatures
                            bodiesToMove = adsk.core.ObjectCollection.create()
                            for body in newBodies:
                                bodiesToMove.add(body)
                            transform = adsk.core.Matrix3D.create()
                            transform.translation = adsk.core.Vector3D.create(-comX, -comY, -minZ)
                            moveInput = moveFeats.createInput(bodiesToMove, transform)
                            moveFeats.add(moveInput)

                    progressDialog.progressValue = 10
                    progressDialog.message = 'Complete!'
                    append_status(inputs, 'Import complete.')

                    for sketch in sketches:
                        sketch.isLightBulbOn = False

                    progressDialog.hide()
                except Exception as e:
                    if 'progressDialog' in locals():
                        progressDialog.hide()
                    append_status(command.commandInputs, f'Error: {e}')
                    if ui:
                        ui.messageBox(f"Import failed:\n\n{str(e)}")

        class YBladeInputChangedHandler(adsk.core.InputChangedEventHandler):
            def __init__(self):
                super().__init__()

            def notify(self, args):
                try:
                    changed = args.input
                    inputs = args.inputs

                    if changed.id == 'profileBrowse':
                        file_path = open_file_dialog(ui, 'Select airfoil file', '*.afl')
                        if file_path:
                            inputs.itemById('profilePath').value = file_path
                            append_status(inputs, f'Airfoil selected: {os.path.basename(file_path)}')
                        changed.value = False

                    elif changed.id == 'bladeBrowse':
                        file_path = open_file_dialog(ui, 'Select blade file', '*.bld')
                        if file_path:
                            inputs.itemById('bladePath').value = file_path
                            append_status(inputs, f'Blade file selected: {os.path.basename(file_path)}')
                        changed.value = False

                except Exception as err:
                    if ui:
                        ui.messageBox(f'Browse failed: {err}')

        class YBladeDestroyHandler(adsk.core.CommandEventHandler):
            def __init__(self):
                super().__init__()
            def notify(self, args):
                sys.stdout.close()

        class YBladeCreateHandler(adsk.core.CommandCreatedEventHandler):
            def __init__(self):
                super().__init__()        
            def notify(self, args):
                try:
                    cmd = args.command
                    onExecute = YBladeExecuteHandler()
                    cmd.execute.add(onExecute)
                    onDestroy = YBladeDestroyHandler()
                    cmd.destroy.add(onDestroy)
                    onInputChanged = YBladeInputChangedHandler()
                    cmd.inputChanged.add(onInputChanged)
                    # keep the handler referenced beyond this function
                    handlers.append(onExecute)
                    handlers.append(onDestroy)
                    handlers.append(onInputChanged)

                    inputs = cmd.commandInputs

                    profilePathInput = inputs.addStringValueInput('profilePath', 'Airfoil file (.afl)', defaultProfilePath)
                    profilePathInput.isReadOnly = False
                    profileBrowse = inputs.addBoolValueInput('profileBrowse', 'Browse airfoil...', False, '', False)
                    profileBrowse.isFullWidth = True

                    bladePathInput = inputs.addStringValueInput('bladePath', 'Blade file (.bld)', defaultBladePath)
                    bladePathInput.isReadOnly = False
                    bladeBrowse = inputs.addBoolValueInput('bladeBrowse', 'Browse blade file...', False, '', False)
                    bladeBrowse.isFullWidth = True

                    inputs.addBoolValueInput('removeHubRadius', 'Start blade at Z=0', True, '', True)
                    inputs.addBoolValueInput('centerMass', 'Center mass to origin', True, '', False)

                    statusBox = inputs.addTextBoxCommandInput('statusLog', 'Status', 'Ready', 6, True)
                    statusBox.isFullWidth = True
                except:
                    if ui:
                        ui.messageBox("Failed:\n{}".format(traceback.format_exc()))

        cmdDef = commandDefinitions.itemById("YBlade")
        if not cmdDef:
            cmdDef = commandDefinitions.addButtonDefinition(
                "YBlade",
                "Import QBlade",
                "Create a blade.",
                "./resources"
            )
        workspace = ui.workspaces.itemById('FusionSolidEnvironment')
        if workspace:
            utilitiesPanel = workspace.toolbarPanels.itemById('SolidScriptsAddinsPanel')
            if utilitiesPanel and not utilitiesPanel.controls.itemById('YBlade'):
                control = utilitiesPanel.controls.addCommand(cmdDef)
                control.isPromoted = True
    
        onCommandCreated = YBladeCreateHandler()
        cmdDef.commandCreated.add(onCommandCreated)
        # keep the handler referenced beyond this function
        handlers.append(onCommandCreated)
        inputs = adsk.core.NamedValues.create()
        cmdDef.execute(inputs)
        adsk.autoTerminate(False)
    except:
        print("Failed:\n{}".format(traceback.format_exc()))
        if ui:
            ui.messageBox("Failed:\n{}".format(traceback.format_exc()))
