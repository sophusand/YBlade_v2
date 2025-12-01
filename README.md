# YBlade - Import QBlade blades into Fusion 360

Script for Fusion 360 that imports [QBlade](https://www.q-blade.org/) blade designs and
constructs them as solid 3D bodies:

![Blade Import Demo](Blade%20importing.gif)

## ✨ Features

- Imports QBlade blade designs directly into Fusion 360 as a single clean solid body
- Automatically detects and uses the dominant airfoil profile in multi-profile blades
- Optional **Start blade at Z=0** toggle removes the hub offset before modelling
- Optional **Center mass to origin** toggle repositions the resulting body using its center of mass
- Built-in status log keeps you updated on every step of the import
- Adds a toolbar button (Solid workspace → Add-Ins panel) for one-click access with a custom icon

## 📋 Supported QBlade Versions

This script supports both:
- **QBlade CE v2.x** (2025) - New `.bld` format with extended parameters
- **QBlade v0.963** (2021) - Old text format

## 🚀 Installation

### Method 1: Direct Install (Recommended)
1. Download or clone this repository
2. Copy the entire `YBlade_v2` folder to your Fusion 360 scripts directory:
   - **Windows**: `%appdata%\Autodesk\Autodesk Fusion 360\API\Scripts`
   - **macOS**: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Scripts`
3. Restart Fusion 360

### Method 2: Manual Install
1. In Fusion 360, go to **Tools & Utilities** → **Add-Ins** → **Scripts and Add-Ins**
2. Click the **"+"** button next to "My Scripts"
3. Select the `YBlade_v2` folder
4. The script should now appear in the list

## 📖 Usage

### Step 1: Prepare QBlade Files

In QBlade, you need to export two files:

1. **Blade Definition File** (`.bld` or `.txt`)
   - In QBlade v2.x: File → Export Blade → Save as `.bld`
   - Contains: positions, chord lengths, twist angles, etc.

2. **Airfoil Profile File** (`.afl` or `.txt`)
   - In QBlade: Airfoils → Select your profile → Export
   - Contains: X-Y coordinates of the airfoil shape

**Important**: Make sure you export the profile that is used most in your blade design.

### Step 2: Run Script in Fusion 360

1. Open Fusion 360 and create or open a design
2. Go to **Tools & Utilities** → **Add-Ins** → **Scripts and Add-Ins**
3. Under **Scripts** tab, find **YBlade** in the list
4. Select it and click **Run**
5. A dialog will appear - click **OK**
6. Select your **blade definition file** (`.bld` or `.txt`)
7. Select your **airfoil profile file** (`.afl` or `.txt`)
8. Optionally toggle:
   - **Start blade at Z=0** to subtract the hub radius so the blade begins at Z = 0 cm
   - **Center mass to origin** to move the finished body so its COM sits at (0,0,0) and the root touches Z = 0
9. Click **OK** and watch the status log for progress updates while the solid is generated

### Step 3: Result

One solid body will be created, following the blade's sweep path and twist profile. You can continue modelling, add mounting hardware, or export it straight to CAM.

## 📁 Example Files

See the `bladeExample` folder for sample input files that work with this script.

## 🔧 Troubleshooting

### "Multiple profiles detected" 
- **Solution**: The script automatically uses the most common profile. Make sure you select the corresponding `.afl` file.

### Blade looks deformed at the root
- **Cause**: Your blade uses circular profiles at the root that differ from the main airfoil
- **Solution**: The script now automatically filters out circular root sections. Use the main airfoil `.afl` file.

### "Guide rails do not intersect"
- **Cause**: Complex blade geometry with extreme twists
- **Solution**: The script now uses simplified loft without guide rails for better reliability

### Script fails to run
- Check that both files are valid QBlade exports
- Ensure the profile file matches the airfoil used in the blade
- Try increasing the "Infill simplification factor" for complex geometries

## ⚠️ Known Limitations

- **Multi-profile blades**: Sections using different airfoils will have their geometry preserved (position, twist, chord), but all will use the same airfoil shape (the most common one)
- **Circular root sections**: Automatically filtered out to maintain consistency
- **Very complex geometries**: May require manual adjustment of simplification parameters

## 📝 Tips for Best Results

1. **Design with single airfoil**: For most accurate results, use one airfoil profile throughout your blade in QBlade
2. **Avoid extreme twists**: Very high twist angles (>60°) near transitions may cause issues
3. **Check your exports**: Verify files open correctly in a text editor before importing
4. **Start simple**: Test with example files first to understand the workflow

## 📦 Recent Updates

- **2025-12-01**: Solid-only workflow, status logging, toolbar button, hub-offset removal, center-of-mass positioning. Removed preview sketch option due to reliability issues in Fusion.

## 🙏 Credits

Original script by Jan Mrázek (2021)  
Updated for QBlade CE v2.x compatibility (2025)  
Fixes and improvements by [Fysik Klubben](https://www.instagram.com/fysik_klubben/)
