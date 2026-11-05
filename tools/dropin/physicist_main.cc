// «Проект физика» для проверки конфликтов имён (tools/e2e.sh, часть 5).
//
// Здесь свой DetectorConstruction с самым обычным именем, как в любом проекте Geant4,
// и две сцены mcscene: A подключена заголовком, B создаётся в make_second.cc.
// Всё это собирается в одну программу, только если у сцен свои пространства имён.

#include <iostream>
#include <string>

#include "G4LogicalVolume.hh"
#include "G4VPhysicalVolume.hh"
#include "G4VUserDetectorConstruction.hh"

#include "DetectorConstruction.hh"   // сцена A: user/DetectorConstruction.hh

// Свой класс физика: глобальный и с тем же именем, что у класса сцены.
class DetectorConstruction : public G4VUserDetectorConstruction {
 public:
  G4VPhysicalVolume* Construct() override { return nullptr; }
};

G4VUserDetectorConstruction* MakeSecondScene();   // make_second.cc, сцена B

namespace {

// Имена объёмов, которые лежат прямо в мире: по ним видно, чья геометрия построилась.
std::string TopVolumes(G4VPhysicalVolume* world) {
  std::string names;
  G4LogicalVolume* lv = world->GetLogicalVolume();
  for (std::size_t i = 0; i < lv->GetNoDaughters(); ++i) {
    if (!names.empty()) names += ",";
    names += lv->GetDaughter(i)->GetName();
  }
  return names;
}

}  // namespace

int main() {
  DetectorConstruction mine;                          // класс физика
  NS_A::DetectorConstruction sceneA;                  // сцена A
  G4VUserDetectorConstruction* sceneB = MakeSecondScene();

  const bool mineOk = (mine.Construct() == nullptr);
  G4VPhysicalVolume* worldA = sceneA.Construct();
  G4VPhysicalVolume* worldB = sceneB->Construct();

  std::cout << "dropin: свой DetectorConstruction " << (mineOk ? "OK" : "НЕ ТОТ") << "\n";
  std::cout << "dropin: сцена A: " << TopVolumes(worldA) << "\n";
  std::cout << "dropin: сцена B: " << TopVolumes(worldB) << "\n";
  return mineOk ? 0 : 1;
}
