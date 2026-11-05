// Вторая сцена для tools/dropin. Отдельный файл нужен потому, что файлы у всех сцен
// называются одинаково (DetectorConstruction.hh): этот .cc собирается с include сцены B.

#include "DetectorConstruction.hh"   // сцена B: user/DetectorConstruction.hh

G4VUserDetectorConstruction* MakeSecondScene() { return new NS_B::DetectorConstruction; }
