// Тесты g4scene. Главное здесь — что наша матрица и Geant4 понимают поворот одинаково:
// без этого на этапе 2 (повороты) любая ошибка будет выглядеть как «тело не там».
//
// Запуск: ctest --test-dir build/g4scene --output-on-failure
// или напрямую: build/g4scene/test_g4scene

#include <cmath>
#include <string>

#include "G4Box.hh"
#include "G4LogicalVolume.hh"
#include "G4Material.hh"
#include "G4Navigator.hh"
#include "G4PVPlacement.hh"
#include "G4Point3D.hh"
#include "G4SystemOfUnits.hh"
#include "G4ios.hh"

#include "g4scene/Materials.hh"
#include "g4scene/Registry.hh"
#include "g4scene/Transform.hh"

namespace {

int gChecks = 0;
int gFailures = 0;

#define CHECK(cond)                                                                \
  do {                                                                             \
    ++gChecks;                                                                     \
    if (!(cond)) {                                                                 \
      ++gFailures;                                                                 \
      G4cerr << __FILE__ << ":" << __LINE__ << ": НЕ ВЫПОЛНЕНО: " #cond << G4endl; \
    }                                                                              \
  } while (0)

bool Near(double a, double b, double tol = 1e-12) { return std::abs(a - b) <= tol; }

bool Near(const G4Point3D& p, double x, double y, double z, double tol = 1e-9) {
  return Near(p.x(), x, tol) && Near(p.y(), y, tol) && Near(p.z(), z, tol);
}

// Произвольная правильная матрица без симметрий: R = Rz(70°)·Ry(-45°)·Rx(30°),
// как euler_xyz_extrinsic_deg [30, -45, 70] в контракте.
g4scene::Mat3 ArbitraryRotation() {
  const double a = 30 * deg, b = -45 * deg, c = 70 * deg;
  const g4scene::Mat3 rx{{{1, 0, 0}, {0, std::cos(a), -std::sin(a)}, {0, std::sin(a), std::cos(a)}}};
  const g4scene::Mat3 ry{{{std::cos(b), 0, std::sin(b)}, {0, 1, 0}, {-std::sin(b), 0, std::cos(b)}}};
  const g4scene::Mat3 rz{{{std::cos(c), -std::sin(c), 0}, {std::sin(c), std::cos(c), 0}, {0, 0, 1}}};
  auto mul = [](const g4scene::Mat3& p, const g4scene::Mat3& q) {
    g4scene::Mat3 r{};
    for (int i = 0; i < 3; ++i)
      for (int j = 0; j < 3; ++j)
        for (int k = 0; k < 3; ++k) r[i][j] += p[i][k] * q[k][j];
    return r;
  };
  return mul(rz, mul(ry, rx));
}

const g4scene::Mat3 kRz90{{{0, -1, 0}, {1, 0, 0}, {0, 0, 1}}};

// --- повороты -------------------------------------------------------------------

void TestRz90TurnsXIntoY() {
  const G4Transform3D t = g4scene::Transform(kRz90, G4ThreeVector());
  CHECK(Near(t * G4Point3D(1, 0, 0), 0, 1, 0));
  CHECK(Near(t * G4Point3D(0, 1, 0), -1, 0, 0));
  CHECK(Near(t * G4Point3D(0, 0, 1), 0, 0, 1));
}

void TestRotateThenShift() {
  // сначала поворот, потом сдвиг: (1,0,0) -> (0,1,0) -> (100,1,0).
  // Если бы сдвиг шёл первым, получилось бы (0,101,0).
  const G4Transform3D t = g4scene::Transform(kRz90, G4ThreeVector(100, 0, 0));
  CHECK(Near(t * G4Point3D(1, 0, 0), 100, 1, 0));
  CHECK(Near(t * G4Point3D(0, 0, 0), 100, 0, 0));
}

void TestElementsAreKeptAsIs() {
  const g4scene::Mat3 m = ArbitraryRotation();
  const G4RotationMatrix r = g4scene::ToRotation(m);
  for (int i = 0; i < 3; ++i)
    for (int j = 0; j < 3; ++j) CHECK(Near(r(i, j), m[i][j]));

  // и точка переводится как m·p + t
  const G4ThreeVector shift(10, -20, 30);
  const G4Transform3D t = g4scene::Transform(m, shift);
  const double p[3] = {1.5, -2.0, 7.0};
  double q[3];
  for (int i = 0; i < 3; ++i) q[i] = m[i][0] * p[0] + m[i][1] * p[1] + m[i][2] * p[2] + shift[i];
  CHECK(Near(t * G4Point3D(p[0], p[1], p[2]), q[0], q[1], q[2]));
}

void TestRowsKeepsRowOrder() {
  // Rows — та же матрица по строкам: первая скобка — первая строка
  constexpr g4scene::Mat3 m = g4scene::Rows({1, 2, 3}, {4, 5, 6}, {7, 8, 9});
  static_assert(m[0][1] == 2 && m[1][0] == 4 && m[2][2] == 9, "Rows: строки не на своих местах");
  CHECK(m[0][2] == 3 && m[2][0] == 7);

  // так генератор пишет поворот на 90° вокруг z: столбцы выровнены пробелами
  const g4scene::Mat3 rz = g4scene::Rows({0, -1, 0},
                                         {1,  0, 0},
                                         {0,  0, 1});
  for (int i = 0; i < 3; ++i)
    for (int j = 0; j < 3; ++j) CHECK(rz[i][j] == kRz90[i][j]);

  // и Transform понимает её так же: ось x тела смотрит вдоль +y родителя
  const G4Transform3D t = g4scene::Transform(rz, G4ThreeVector());
  CHECK(Near(t * G4Point3D(1, 0, 0), 0, 1, 0));
}

void TestRotationProblem() {
  CHECK(g4scene::RotationProblem(g4scene::kIdentity).empty());
  CHECK(g4scene::RotationProblem(kRz90).empty());
  CHECK(g4scene::RotationProblem(ArbitraryRotation()).empty());

  const g4scene::Mat3 mirror{{{1, 0, 0}, {0, 1, 0}, {0, 0, -1}}};               // det = -1
  CHECK(g4scene::RotationProblem(mirror).find("det") != std::string::npos);

  const g4scene::Mat3 scaled{{{2, 0, 0}, {0, 1, 0}, {0, 0, 1}}};                // масштаб
  CHECK(g4scene::RotationProblem(scaled).find("ортонорм") != std::string::npos);

  const g4scene::Mat3 rough{{{1, 1e-6, 0}, {0, 1, 0}, {0, 0, 1}}};              // грубее допуска
  CHECK(!g4scene::RotationProblem(rough).empty());

  const g4scene::Mat3 nan{{{NAN, 0, 0}, {0, 1, 0}, {0, 0, 1}}};
  CHECK(!g4scene::RotationProblem(nan).empty());
}

// --- размещение -----------------------------------------------------------------

// Geant4 должен понять наш поворот как активный «тело -> родитель».
// Родитель повёрнут на 90° вокруг z, ребёнок сдвинут внутри него на (30, 0, 0).
// Правильно: ребёнок в мире в (0, 30, 0). Если поворот понят как обратный — в (0, -30, 0).
void TestPlaceUsesActiveRotation() {
  g4scene::Registry reg;
  reg.AddMaterial("air", g4scene::Nist("G4_AIR"));
  reg.AddMaterial("iron", g4scene::Nist("G4_Fe"));

  auto* worldLV = new G4LogicalVolume(new G4Box("t_world", 200 * mm, 200 * mm, 200 * mm),
                                      reg.GetMaterial("air"), "t_world");
  auto* worldPV = new G4PVPlacement(nullptr, G4ThreeVector(), worldLV, "t_world", nullptr, false, 0);

  auto* parentLV = new G4LogicalVolume(new G4Box("t_parent", 50 * mm, 50 * mm, 10 * mm),
                                       reg.GetMaterial("air"), "t_parent");
  auto* parentPV = g4scene::Place(parentLV, worldLV, "t_parent",
                                  g4scene::Transform(kRz90, G4ThreeVector()));

  auto* childLV = new G4LogicalVolume(new G4Box("t_child", 5 * mm, 5 * mm, 5 * mm),
                                      reg.GetMaterial("iron"), "t_child");
  g4scene::Place(childLV, parentLV, "t_child",
                 g4scene::Transform(g4scene::kIdentity, G4ThreeVector(30 * mm, 0, 0)));

  // Geant4 хранит у размещения тот же поворот, что мы дали
  const G4RotationMatrix stored = parentPV->GetObjectRotationValue();
  for (int i = 0; i < 3; ++i)
    for (int j = 0; j < 3; ++j) CHECK(Near(stored(i, j), kRz90[i][j]));

  G4Navigator nav;
  nav.SetWorldVolume(worldPV);
  auto where = [&nav](double x, double y, double z) {
    const G4VPhysicalVolume* pv =
        nav.LocateGlobalPointAndSetup(G4ThreeVector(x, y, z), nullptr, false, true);
    return pv ? std::string(pv->GetName()) : std::string("<снаружи>");
  };
  CHECK(where(0, 30 * mm, 0) == "t_child");
  CHECK(where(0, -30 * mm, 0) == "t_parent");
  CHECK(where(30 * mm, 0, 0) == "t_parent");
  CHECK(where(150 * mm, 0, 0) == "t_world");

  const G4VPhysicalVolume* inChild =
      nav.LocateGlobalPointAndSetup(G4ThreeVector(0, 33 * mm, 2 * mm), nullptr, false, true);
  CHECK(inChild != nullptr && inChild->GetLogicalVolume()->GetMaterial()->GetName() == "G4_Fe");
}

// --- реестр и материалы ---------------------------------------------------------

void TestRegistryAndNist() {
  g4scene::Registry reg;
  G4Material* fe = g4scene::Nist("G4_Fe");
  CHECK(fe != nullptr && fe->GetName() == "G4_Fe");
  CHECK(g4scene::Nist("G4_Fe") == fe);                       // второй раз — тот же объект

  reg.AddMaterial("iron", fe);
  CHECK(reg.GetMaterial("iron") == fe);
  CHECK(reg.FindMaterial("steel") == nullptr);
  CHECK(reg.NumMaterials() == 1);

  auto* lv = new G4LogicalVolume(new G4Box("r_box", 1 * mm, 1 * mm, 1 * mm), fe, "r_box");
  reg.AddVolume("Body", lv);
  CHECK(reg.GetVolume("Body") == lv);
  CHECK(reg.FindVolume("world") == nullptr);
}

}  // namespace

int main() {
  TestRz90TurnsXIntoY();
  TestRotateThenShift();
  TestElementsAreKeptAsIs();
  TestRowsKeepsRowOrder();
  TestRotationProblem();
  TestPlaceUsesActiveRotation();
  TestRegistryAndNist();

  if (gFailures != 0) {
    G4cerr << "g4scene: НЕ ПРОШЛО " << gFailures << " из " << gChecks << " проверок" << G4endl;
    return 1;
  }
  G4cout << "g4scene: OK, " << gChecks << " проверок" << G4endl;
  return 0;
}
