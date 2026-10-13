// g4scene — маленькая библиотека, которой пользуется сгенерированный код.
//
// Повороты и размещение тел.
//
// Соглашение контракта jinr-mc-scene: матрица m задана по строкам, её столбцы —
// оси тела в системе родителя, точка тела p попадает в систему родителя как m·p + t
// (активный поворот «тело -> родитель»).
//
// Geant4 умеет размещать тело двумя способами, и они понимают поворот по-разному:
//   - G4PVPlacement(G4RotationMatrix*, G4ThreeVector, ...) ждёт поворот СИСТЕМЫ
//     (обратный к нашему) — легко перепутать;
//   - G4PVPlacement(G4Transform3D, ...) ждёт ровно наш активный поворот.
// Поэтому размещаем всегда через G4Transform3D, функцией Place.
#pragma once

#include <array>
#include <string>

#include "G4RotationMatrix.hh"
#include "G4String.hh"
#include "G4ThreeVector.hh"
#include "G4Transform3D.hh"

class G4LogicalVolume;
class G4VPhysicalVolume;

namespace scene {

using Mat3 = std::array<std::array<double, 3>, 3>;   // по строкам, как в JSON

inline constexpr Mat3 kIdentity{{{1, 0, 0}, {0, 1, 0}, {0, 0, 1}}};

// Допуск проверки поворота. Генератор доводит матрицы до ортонормированных
// с точностью ~1e-15, так что 1e-9 — с большим запасом.
inline constexpr double kRotationTolerance = 1e-9;

// Пустая строка, если m — правильный поворот (M·Mᵀ = I и det = +1);
// иначе текст проблемы. Ничего не бросает — удобно для тестов.
std::string RotationProblem(const Mat3& m, double tolerance = kRotationTolerance);

// То же, но при проблеме — G4Exception (FatalException).
void CheckRotation(const Mat3& m, const G4String& where = "");

// Матрица контракта -> G4RotationMatrix с теми же элементами: r(i, j) == m[i][j].
G4RotationMatrix ToRotation(const Mat3& m);

// Активное преобразование «тело -> родитель»: сначала поворот m, потом сдвиг t.
// Бросает G4Exception, если m — не поворот.
G4Transform3D Transform(const Mat3& m, const G4ThreeVector& t);

// Разместить логический объём lv в mother через G4Transform3D.
G4VPhysicalVolume* Place(G4LogicalVolume* lv, G4LogicalVolume* mother,
                         const G4String& name, const G4Transform3D& t,
                         bool checkOverlaps = false);

}  // namespace scene
