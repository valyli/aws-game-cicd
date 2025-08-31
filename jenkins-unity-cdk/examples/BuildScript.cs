using System;
using System.IO;
using UnityEditor;
using UnityEngine;

/// <summary>
/// Unity build script for CI/CD pipeline
/// This script provides methods to build Unity projects from command line
/// </summary>
public class BuildScript
{
    /// <summary>
    /// Main build method called from Jenkins pipeline
    /// </summary>
    public static void Build()
    {
        try
        {
            // Get command line arguments
            string[] args = Environment.GetCommandLineArgs();
            string buildTarget = GetArgument(args, "-customBuildTarget", "StandaloneLinux64");
            string buildName = GetArgument(args, "-customBuildName", "UnityBuild");
            string buildPath = GetArgument(args, "-customBuildPath", "Builds");
            
            Debug.Log($"Starting build for target: {buildTarget}");
            Debug.Log($"Build name: {buildName}");
            Debug.Log($"Build path: {buildPath}");
            
            // Parse build target
            BuildTarget target = ParseBuildTarget(buildTarget);
            
            // Get scenes to build
            string[] scenes = GetScenesInBuild();
            
            // Set build options
            BuildOptions options = BuildOptions.None;
            
            // Check for development build
            if (HasArgument(args, "-development"))
            {
                options |= BuildOptions.Development;
                Debug.Log("Development build enabled");
            }
            
            // Set output path
            string outputPath = Path.Combine(buildPath, buildTarget, buildName);
            
            // Add platform-specific extension
            outputPath = AddPlatformExtension(outputPath, target);
            
            // Ensure output directory exists
            Directory.CreateDirectory(Path.GetDirectoryName(outputPath));
            
            Debug.Log($"Output path: {outputPath}");
            
            // Configure platform-specific settings
            ConfigurePlatformSettings(target);
            
            // Build player
            BuildPlayerOptions buildPlayerOptions = new BuildPlayerOptions
            {
                scenes = scenes,
                locationPathName = outputPath,
                target = target,
                options = options
            };
            
            var report = BuildPipeline.BuildPlayer(buildPlayerOptions);
            
            // Check build result
            if (report.summary.result == UnityEditor.Build.Reporting.BuildResult.Succeeded)
            {
                Debug.Log($"Build succeeded: {report.summary.outputPath}");
                Debug.Log($"Build size: {report.summary.totalSize} bytes");
                Debug.Log($"Build time: {report.summary.totalTime}");
                
                // Create build info file
                CreateBuildInfo(outputPath, report, buildTarget, buildName);
                
                EditorApplication.Exit(0);
            }
            else
            {
                Debug.LogError($"Build failed with result: {report.summary.result}");
                
                // Log build errors
                foreach (var step in report.steps)
                {
                    foreach (var message in step.messages)
                    {
                        if (message.type == UnityEditor.Build.Reporting.LogType.Error)
                        {
                            Debug.LogError($"Build Error: {message.content}");
                        }
                    }
                }
                
                EditorApplication.Exit(1);
            }
        }
        catch (Exception e)
        {
            Debug.LogError($"Build script exception: {e.Message}");
            Debug.LogError($"Stack trace: {e.StackTrace}");
            EditorApplication.Exit(1);
        }
    }
    
    /// <summary>
    /// Build for Android platform
    /// </summary>
    public static void BuildAndroid()
    {
        SetBuildTarget("Android");
        Build();
    }
    
    /// <summary>
    /// Build for iOS platform
    /// </summary>
    public static void BuildiOS()
    {
        SetBuildTarget("iOS");
        Build();
    }
    
    /// <summary>
    /// Build for WebGL platform
    /// </summary>
    public static void BuildWebGL()
    {
        SetBuildTarget("WebGL");
        Build();
    }
    
    /// <summary>
    /// Build for Windows Standalone
    /// </summary>
    public static void BuildWindows()
    {
        SetBuildTarget("StandaloneWindows64");
        Build();
    }
    
    /// <summary>
    /// Build for Linux Standalone
    /// </summary>
    public static void BuildLinux()
    {
        SetBuildTarget("StandaloneLinux64");
        Build();
    }
    
    private static void SetBuildTarget(string target)
    {
        Environment.SetEnvironmentVariable("CUSTOM_BUILD_TARGET", target);
    }
    
    private static string GetArgument(string[] args, string name, string defaultValue = "")
    {
        for (int i = 0; i < args.Length; i++)
        {
            if (args[i] == name && i + 1 < args.Length)
            {
                return args[i + 1];
            }
        }
        
        // Check environment variable
        string envValue = Environment.GetEnvironmentVariable(name.TrimStart('-').ToUpper().Replace('-', '_'));
        return !string.IsNullOrEmpty(envValue) ? envValue : defaultValue;
    }
    
    private static bool HasArgument(string[] args, string name)
    {
        for (int i = 0; i < args.Length; i++)
        {
            if (args[i] == name)
            {
                return true;
            }
        }
        return false;
    }
    
    private static BuildTarget ParseBuildTarget(string buildTarget)
    {
        switch (buildTarget.ToLower())
        {
            case "android":
                return BuildTarget.Android;
            case "ios":
                return BuildTarget.iOS;
            case "webgl":
                return BuildTarget.WebGL;
            case "standalonewindows64":
                return BuildTarget.StandaloneWindows64;
            case "standalonelinux64":
                return BuildTarget.StandaloneLinux64;
            case "standaloneosx":
                return BuildTarget.StandaloneOSX;
            default:
                Debug.LogWarning($"Unknown build target: {buildTarget}, defaulting to StandaloneLinux64");
                return BuildTarget.StandaloneLinux64;
        }
    }
    
    private static string[] GetScenesInBuild()
    {
        var scenes = new string[EditorBuildSettings.scenes.Length];
        for (int i = 0; i < scenes.Length; i++)
        {
            scenes[i] = EditorBuildSettings.scenes[i].path;
        }
        
        if (scenes.Length == 0)
        {
            Debug.LogWarning("No scenes found in build settings, using all scenes in Assets folder");
            var sceneGuids = AssetDatabase.FindAssets("t:Scene");
            scenes = new string[sceneGuids.Length];
            for (int i = 0; i < sceneGuids.Length; i++)
            {
                scenes[i] = AssetDatabase.GUIDToAssetPath(sceneGuids[i]);
            }
        }
        
        return scenes;
    }
    
    private static string AddPlatformExtension(string path, BuildTarget target)
    {
        switch (target)
        {
            case BuildTarget.StandaloneWindows64:
                return path + ".exe";
            case BuildTarget.Android:
                return path + ".apk";
            case BuildTarget.iOS:
                return path; // iOS builds to a folder
            case BuildTarget.WebGL:
                return path; // WebGL builds to a folder
            case BuildTarget.StandaloneLinux64:
                return path; // Linux executable without extension
            case BuildTarget.StandaloneOSX:
                return path + ".app";
            default:
                return path;
        }
    }
    
    private static void ConfigurePlatformSettings(BuildTarget target)
    {
        switch (target)
        {
            case BuildTarget.Android:
                ConfigureAndroidSettings();
                break;
            case BuildTarget.iOS:
                ConfigureiOSSettings();
                break;
            case BuildTarget.WebGL:
                ConfigureWebGLSettings();
                break;
        }
    }
    
    private static void ConfigureAndroidSettings()
    {
        Debug.Log("Configuring Android build settings...");
        
        // Set Android SDK path
        string androidSdkPath = Environment.GetEnvironmentVariable("ANDROID_HOME");
        if (!string.IsNullOrEmpty(androidSdkPath))
        {
            EditorPrefs.SetString("AndroidSdkRoot", androidSdkPath);
        }
        
        // Configure Android player settings
        PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;
        PlayerSettings.Android.minSdkVersion = AndroidSdkVersions.AndroidApiLevel24;
        PlayerSettings.Android.targetSdkVersion = AndroidSdkVersions.AndroidApiLevelAuto;
        
        // Set keystore if available
        string keystorePath = Environment.GetEnvironmentVariable("ANDROID_KEYSTORE_PATH");
        string keystorePass = Environment.GetEnvironmentVariable("ANDROID_KEYSTORE_PASS");
        string keyaliasName = Environment.GetEnvironmentVariable("ANDROID_KEYALIAS_NAME");
        string keyaliasPass = Environment.GetEnvironmentVariable("ANDROID_KEYALIAS_PASS");
        
        if (!string.IsNullOrEmpty(keystorePath) && File.Exists(keystorePath))
        {
            PlayerSettings.Android.keystoreName = keystorePath;
            PlayerSettings.Android.keystorePass = keystorePass;
            PlayerSettings.Android.keyaliasName = keyaliasName;
            PlayerSettings.Android.keyaliasPass = keyaliasPass;
            Debug.Log("Android keystore configured");
        }
        else
        {
            Debug.LogWarning("Android keystore not configured, using debug keystore");
        }
    }
    
    private static void ConfigureiOSSettings()
    {
        Debug.Log("Configuring iOS build settings...");
        
        // Configure iOS player settings
        PlayerSettings.iOS.targetOSVersionString = "12.0";
        PlayerSettings.iOS.sdkVersion = iOSSdkVersion.DeviceSDK;
        
        // Set team ID if available
        string teamId = Environment.GetEnvironmentVariable("IOS_TEAM_ID");
        if (!string.IsNullOrEmpty(teamId))
        {
            PlayerSettings.iOS.appleDeveloperTeamID = teamId;
            Debug.Log($"iOS Team ID set to: {teamId}");
        }
    }
    
    private static void ConfigureWebGLSettings()
    {
        Debug.Log("Configuring WebGL build settings...");
        
        // Configure WebGL player settings
        PlayerSettings.WebGL.compressionFormat = WebGLCompressionFormat.Gzip;
        PlayerSettings.WebGL.memorySize = 512;
        PlayerSettings.WebGL.exceptionSupport = WebGLExceptionSupport.None;
    }
    
    private static void CreateBuildInfo(string buildPath, UnityEditor.Build.Reporting.BuildReport report, string buildTarget, string buildName)
    {
        try
        {
            string buildInfoPath = Path.Combine(Path.GetDirectoryName(buildPath), "build-info.json");
            
            var buildInfo = new
            {
                buildName = buildName,
                buildTarget = buildTarget,
                buildTime = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                unityVersion = Application.unityVersion,
                buildSize = report.summary.totalSize,
                buildDuration = report.summary.totalTime.TotalSeconds,
                buildResult = report.summary.result.ToString(),
                outputPath = report.summary.outputPath,
                platform = Application.platform.ToString(),
                gitCommit = Environment.GetEnvironmentVariable("GIT_COMMIT") ?? "unknown",
                buildNumber = Environment.GetEnvironmentVariable("BUILD_NUMBER") ?? "unknown",
                jobName = Environment.GetEnvironmentVariable("JOB_NAME") ?? "unknown"
            };
            
            string json = JsonUtility.ToJson(buildInfo, true);
            File.WriteAllText(buildInfoPath, json);
            
            Debug.Log($"Build info saved to: {buildInfoPath}");
        }
        catch (Exception e)
        {
            Debug.LogWarning($"Failed to create build info: {e.Message}");
        }
    }
}