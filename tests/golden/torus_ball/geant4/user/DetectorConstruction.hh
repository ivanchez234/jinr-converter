// Этот файл mcscene создал один раз, и дальше он ваш: генератор его не
// перезаписывает, даже с --force. Здесь удобно дописывать то, чего нет в
// scene.json: цвета, чувствительные детекторы, свои объёмы.
#pragma once

#include "GeneratedDetectorConstruction.hh"

// Пример: объём-детектор (чувствительный объём), в котором Geant4 считает дозу.
// Чтобы включить, поставьте 1 вместо 0 в строке #define ниже и пересоберите.
#ifndef MCSCENE_EXAMPLE_DETECTOR
#define MCSCENE_EXAMPLE_DETECTOR 0
#endif

#if MCSCENE_EXAMPLE_DETECTOR
#include "G4MultiFunctionalDetector.hh"
#include "G4PSDoseDeposit.hh"
#include "G4SDManager.hh"
#endif

namespace torus_ball {   // как в generated/: классы сцены — в пространстве имён сцены

class DetectorConstruction : public GeneratedDetectorConstruction {
 public:
#if MCSCENE_EXAMPLE_DETECTOR
  // Чувствительные объёмы. Geant4 вызывает этот метод после Construct()
  // (в многопоточном режиме — в каждом рабочем потоке). Образец — пример B3 из Geant4.
  void ConstructSDandField() override {
    // Тело "ring" — «Медный тор R100 r20, 30° вокруг x, затем 45° вокруг y»; материал: Медь, G4_Cu
    // становится детектором: G4PSDoseDeposit суммирует дозу (энерговыделение / масса) за событие.
    // Чтобы получить числа, нужен свой RunAction, как в примере B3a (G4THitsMap, G4Accumulable).
    auto* detector = new G4MultiFunctionalDetector("dose_ring");
    G4SDManager::GetSDMpointer()->AddNewDetector(detector);
    detector->RegisterPrimitive(new G4PSDoseDeposit("dose"));
    SetSensitiveDetector(LV("ring"), detector);
  }
#endif

 protected:
  // Вызывается сразу после того, как построены материалы сцены:
  // можно поменять свойства материалов или добавить свои через fReg.AddMaterial.
  void ConfigureMaterials() override {}

  // Вызывается, когда вся геометрия сцены построена. Объёмы сцены доступны
  // по id из scene.json: LV("Body"), материалы — Mat("iron").
  void PostConstruct(G4LogicalVolume* /*world*/) override {}
};

}  // namespace torus_ball
