using UnrealBuildTool;
public class PMX4UE : ModuleRules
{
    public PMX4UE(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine", "AnimGraphRuntime" });
        PrivateDependencyModuleNames.AddRange(new[] { "Chaos", "PhysicsCore" });
    }
}
