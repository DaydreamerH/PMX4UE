// Read-only Autodesk SDK diagnostic. Build against the target UE's bundled SDK.
#include <fbxsdk.h>
#include <iostream>
int main(int argc,char** argv) {
    if(argc!=2) return 2;
    auto* manager=FbxManager::Create();
    manager->SetIOSettings(FbxIOSettings::Create(manager,IOSROOT));
    auto* scene=FbxScene::Create(manager,"probe");
    auto* importer=FbxImporter::Create(manager,"");
    if(!importer->Initialize(argv[1],-1,manager->GetIOSettings()) || !importer->Import(scene)) return 3;
    std::cout << "poses=" << scene->GetPoseCount() << " nodes=" << scene->GetNodeCount() << "\n";
    for(int p=0;p<scene->GetPoseCount();++p) {
        auto* pose=scene->GetPose(p); int bad=0;
        std::cout << "POSE " << p << " count=" << pose->GetCount() << " bind=" << pose->IsBindPose() << "\n";
        for(int ni=0;ni<scene->GetNodeCount();++ni) {
            auto* node=scene->GetNode(ni); auto* mesh=node->GetMesh();
            if(!mesh || pose->Find(node)<0) continue;
            for(int si=0;si<mesh->GetDeformerCount(FbxDeformer::eSkin);++si) {
                auto* skin=static_cast<FbxSkin*>(mesh->GetDeformer(si,FbxDeformer::eSkin));
                int printed=0;
                for(int ci=0;ci<skin->GetClusterCount();++ci) {
                    auto* c=skin->GetCluster(ci); int bi=pose->Find(c->GetLink());
                    if(bi<0) continue;
                    FbxAMatrix ref,link; c->GetTransformMatrix(ref); c->GetTransformLinkMatrix(link);
                    auto expected=pose->GetMatrix(bi).Inverse()*pose->GetMatrix(pose->Find(node));
                    FbxMatrix actual(link.Inverse()*ref); double delta=0;
                    for(int r=0;r<4;++r) for(int col=0;col<4;++col) delta=std::max(delta,std::abs(expected.Get(r,col)-actual.Get(r,col)));
                    if(delta>1e-4 && printed++<5) std::cout << "CLUSTER " << c->GetLink()->GetName() << " delta=" << delta << "\n";
                }
            }
        }
        for(int i=0;i<1;++i) {
            auto* n=scene->GetNode(i);
            FbxArray<FbxNode*> ancestors,deformers,deformerAncestors,matrices; FbxStatus status;
            if(!pose->IsValidBindPoseVerbose(n,ancestors,deformers,deformerAncestors,matrices,0.0001,&status)) {
                ++bad;
                if(bad<=5) {
                    std::cout << "BAD " << n->GetName() << " ancestors=" << ancestors.GetCount()
                        << " deformers=" << deformers.GetCount() << " defAnc=" << deformerAncestors.GetCount()
                        << " matrices=" << matrices.GetCount() << " " << status.GetErrorString() << "\n";
                    for(int j=0;j<matrices.GetCount() && j<5;++j) std::cout << "MATRIX " << matrices[j]->GetName() << "\n";
                }
            }
        }
        std::cout << "bad_count=" << bad << "\n";
    }
    manager->Destroy(); return 0;
}
