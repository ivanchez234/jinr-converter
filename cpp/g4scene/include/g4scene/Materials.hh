// Материалы.
//
// Этап 1: только материалы из базы NIST Geant4 (G4_AIR, G4_Fe, G4_CONCRETE, ...).
// Свои составы (scene::Custom) появятся на этапе 3.
#pragma once

#include "G4String.hh"

class G4Material;

namespace scene {

// G4NistManager::FindOrBuildMaterial(name); если такого имени нет — G4Exception.
G4Material* Nist(const G4String& name);

}  // namespace scene
