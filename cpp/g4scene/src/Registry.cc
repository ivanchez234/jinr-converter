#include "g4scene/Registry.hh"

#include <cstdlib>

#include "G4Exception.hh"

namespace scene {

namespace {

[[noreturn]] void Fatal(const char* where, const std::string& message) {
  G4ExceptionDescription ed;
  ed << message;
  G4Exception(where, "g4scene002", FatalException, ed);
  std::abort();   // G4Exception с FatalException сам не возвращается; это для компилятора
}

template <class T>
T* Find(const std::map<std::string, T*>& m, const G4String& id) {
  const auto it = m.find(id);
  return it == m.end() ? nullptr : it->second;
}

}  // namespace

void Registry::AddMaterial(const G4String& id, G4Material* material) {
  if (material == nullptr) Fatal("scene::Registry::AddMaterial", "материал '" + id + "' = nullptr");
  if (!fMaterials.emplace(id, material).second)
    Fatal("scene::Registry::AddMaterial", "материал '" + id + "' добавлен дважды");
}

void Registry::AddVolume(const G4String& id, G4LogicalVolume* volume) {
  if (volume == nullptr) Fatal("scene::Registry::AddVolume", "объём '" + id + "' = nullptr");
  if (!fVolumes.emplace(id, volume).second)
    Fatal("scene::Registry::AddVolume", "объём '" + id + "' добавлен дважды");
}

G4Material* Registry::FindMaterial(const G4String& id) const { return Find(fMaterials, id); }

G4LogicalVolume* Registry::FindVolume(const G4String& id) const { return Find(fVolumes, id); }

G4Material* Registry::GetMaterial(const G4String& id) const {
  G4Material* m = FindMaterial(id);
  if (m == nullptr) Fatal("scene::Registry::GetMaterial", "материал '" + id + "' не найден");
  return m;
}

G4LogicalVolume* Registry::GetVolume(const G4String& id) const {
  G4LogicalVolume* v = FindVolume(id);
  if (v == nullptr) Fatal("scene::Registry::GetVolume", "объём '" + id + "' не найден");
  return v;
}

}  // namespace scene
