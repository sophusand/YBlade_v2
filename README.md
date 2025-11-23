# YBlade - Import QBlade blades into Fusion 360

Script for Fusion 360 that imports [QBlade](https://www.q-blade.org/) blade designs and
constructs them as solid 3D bodies:

![result.png](result.png)

## ✨ Features

- Imports QBlade blade designs directly into Fusion 360
- Generates two solid bodies:
  - **Outer shell**: Smooth swept surface (ready for manufacturing)
  - **Inner infill**: Simplified internal structure (for hollow blades)
- Automatic profile detection and filtering
- Smart handling of multi-profile blades

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
8. Adjust parameters if needed:
   - **Shell thickness**: Wall thickness for hollow blade (default: 1mm)
   - **Infill simplification**: Higher = simpler infill geometry (default: 0.005)
9. Click **OK** and wait for generation to complete

### Step 3: Result

Two bodies will be created:
- **Body 1**: Outer shell (smooth swept surface)
- **Body 2**: Inner infill (simplified internal structure)

You can now use Combine operations to subtract the infill from the shell for a hollow blade.

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

## 🙏 Credits

Original script by Jan Mrázek (2021)  
Updated for QBlade CE v2.x compatibility (2025)
