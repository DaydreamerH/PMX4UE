#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "PMX4UERetargetTools.generated.h"

/** Read-only, engine-resolved retarget poses for the portable pose editor. */
UCLASS()
class PMX4UEEDITOR_API UPMX4UERetargetTools : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable, Category="PMX4UE|Retarget")
    static FString InspectRetargetPose(const FString& RetargeterPath, bool bSource);
};
