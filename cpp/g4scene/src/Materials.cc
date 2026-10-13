#include "g4scene/Materials.hh"

#include "G4Exception.hh"
#include "G4Material.hh"
#include "G4NistManager.hh"

namespace scene {

G4Material* Nist(const G4String& name) {
  G4Material* m = G4NistManager::Instance()->FindOrBuildMaterial(name);
  if (m == nullptr) {
    G4ExceptionDescription ed;
    ed << "материала '" << name << "' нет в базе NIST Geant4 "
       << "(список имён: /material/nist/listMaterials all)";
    G4Exception("scene::Nist", "g4scene003", FatalException, ed);
  }
  return m;
}

}  // namespace scene
