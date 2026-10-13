// Реестр материалов и логических объёмов по id из scene.json.
//
// Сгенерированный код регистрирует всё, что построил, и потом берёт по id:
//   fReg.AddMaterial("iron", scene::Nist("G4_Fe"));
//   ... new G4LogicalVolume(solid, fReg.GetMaterial("iron"), "Body") ...
// Если id нет — понятная ошибка «материал 'steel' не найден», а не падение
// на nullptr где-то в глубине Geant4.
#pragma once

#include <map>
#include <string>

#include "G4String.hh"

class G4LogicalVolume;
class G4Material;

namespace scene {

class Registry {
 public:
  // Добавить. nullptr или повторный id — G4Exception (FatalException).
  void AddMaterial(const G4String& id, G4Material* material);
  void AddVolume(const G4String& id, G4LogicalVolume* volume);

  // Найти: nullptr, если нет.
  G4Material* FindMaterial(const G4String& id) const;
  G4LogicalVolume* FindVolume(const G4String& id) const;

  // Взять: G4Exception (FatalException), если нет.
  G4Material* GetMaterial(const G4String& id) const;
  G4LogicalVolume* GetVolume(const G4String& id) const;

  std::size_t NumMaterials() const { return fMaterials.size(); }
  std::size_t NumVolumes() const { return fVolumes.size(); }

 private:
  std::map<std::string, G4Material*> fMaterials;
  std::map<std::string, G4LogicalVolume*> fVolumes;
};

}  // namespace scene
