# DOS2DE Collada Exporter for Blender

An addon for Blender that allows you to export dae/gr2 files for the game Divinity: Original Sin 2 - Definitive Edition.

## Features:  
* Export to dae, or export to gr2 if the path to divine.exe is set.
* Automatically rotate the object for DOS2's Y-Up world (Blender is Z-Up).
* Use the layer name, active object name, or action name (animations) when exporting.
* Use built-in presets for quick exporting.
* Specify project pathways to skip having to manually navigate to the correct folder when exporting.
* Specific Custom Properties on meshes are exported (Rigid, Cloth, MeshProxy). You can also globally flag your meshes with one of these flags.

## Installing

### Zip Method  
* Download this repository as a zip (using the green Clone or download button).
* Save the addon somewhere where you can find it again.
* Refer to Blender's guide for installing addons here: [Install from File](https://docs.blender.org/manual/en/latest/preferences/addons.html#header).

### Cloning  
* In Blender, navigate to File -> User Preferences -> File.
* The pathway for "Scripts" is where Blender will read new addon folders from. Add a pathway if it's blank.
* [Clone the repository](https://help.github.com/articles/cloning-a-repository/) either in your scripts folder, or somwhere else and copy the `io_scene_dos2de` folder to your scripts folder.

### Activating the Addon  
* In Blender, navigate to File -> User Preferences -> Add-ons
* Either search for "Divinity", or click Community, then Import-Export.
* Check the checkbox next to "Divinity Collada Exporter".

## User Preferences Settings

### Divine Path  
This is the pathway to divine.exe, bundled with Norbyte's Export Tool. If set, the addon can export to the GR2 format, using divine.

### Convert to GR2 by Default  
If checked, "Convert to GR2" will automatically be checked when exporting. Requires divine.exe's path to be set.

### Default Preset  
If set, the addon will default to the selected preset when opening it up for the first time.

### Projects  
Project pathways can be configured for quicker exporting. 

#### Project Folder  
The "root" folder your blend files will be under. This is a parent folder the addon will compare your blend file's pathway against.

#### Export Folder  
When the above folder is found in the blend's pathway, this folder will be the default root when exporting.

### Use Preset Type for Export Subfolder  
If checked and a project folder is detected, the current preset will automatically determine the subfolder. For instance, if you have a project folder set, and an export folder set to Public/Modname_UUID/Assets, then selecting the "Model" preset defaults the exported file to "Assets/Model".

## Credits
This is a heavily modified version of Godot Engine's "Better" Collada Exporter for Blender, located here: [https://github.com/godotengine/collada-exporter](https://github.com/godotengine/collada-exporter)

Special thanks to Norbyte for developing and maintaining [https://github.com/Norbyte/lslib](https://github.com/Norbyte/lslib), which is the sole reason we can even convert models to DOS2's format in the first place. 
