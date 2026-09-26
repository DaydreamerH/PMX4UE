using UnrealBuildTool;
public class PMX4UEEditor : ModuleRules
{
    public PMX4UEEditor(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine" });
        PrivateDependencyModuleNames.AddRange(new[] {
            "PMX4UE", "AnimGraph", "AnimGraphRuntime", "AnimationCore", "AssetRegistry",
            "BlueprintGraph", "Chaos", "EditorScriptingUtilities", "Json", "JsonUtilities",
            "MaterialEditor", "PhysicsCore", "RenderCore", "RHI", "Slate", "SlateCore", "UnrealEd"
        });
    }
}
