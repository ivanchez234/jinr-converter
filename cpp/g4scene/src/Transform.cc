#include "g4scene/Transform.hh"

#include <algorithm>
#include <cmath>
#include <sstream>

#include "G4Exception.hh"
#include "G4LogicalVolume.hh"
#include "G4PVPlacement.hh"

namespace scene {

namespace {

double Det(const Mat3& m) {
  return m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
       - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
       + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]);
}

}  // namespace

std::string RotationProblem(const Mat3& m, double tolerance) {
  for (const auto& row : m)
    for (double x : row)
      if (!std::isfinite(x)) return "в матрице есть NaN или бесконечность";

  double dev = 0.0;                                  // max |(M·Mᵀ)_ij − δ_ij|
  for (int i = 0; i < 3; ++i) {
    for (int j = 0; j < 3; ++j) {
      double s = 0.0;
      for (int k = 0; k < 3; ++k) s += m[i][k] * m[j][k];
      dev = std::max(dev, std::abs(s - (i == j ? 1.0 : 0.0)));
    }
  }
  if (dev > tolerance) {
    std::ostringstream os;
    os << "матрица не ортонормирована: отклонение M*Mт от единичной " << dev
       << " (допуск " << tolerance << ")";
    return os.str();
  }
  if (Det(m) < 0.0) return "det = -1: это отражение, а не поворот";
  return {};
}

void CheckRotation(const Mat3& m, const G4String& where) {
  const std::string problem = RotationProblem(m);
  if (problem.empty()) return;
  G4ExceptionDescription ed;
  ed << "Неправильный поворот" << (where.empty() ? "" : " у ") << where << ": " << problem;
  G4Exception("scene::CheckRotation", "g4scene001", FatalException, ed);
}

G4RotationMatrix ToRotation(const Mat3& m) {
  // Столбцы матрицы — оси тела в системе родителя. rotateAxes строит поворот,
  // который переводит оси x, y, z в эти три вектора, то есть ставит их столбцами.
  const G4ThreeVector ex(m[0][0], m[1][0], m[2][0]);
  const G4ThreeVector ey(m[0][1], m[1][1], m[2][1]);
  const G4ThreeVector ez(m[0][2], m[1][2], m[2][2]);
  G4RotationMatrix r;
  r.rotateAxes(ex, ey, ez);
  return r;
}

G4Transform3D Transform(const Mat3& m, const G4ThreeVector& t) {
  CheckRotation(m);
  return G4Transform3D(ToRotation(m), t);
}

G4VPhysicalVolume* Place(G4LogicalVolume* lv, G4LogicalVolume* mother,
                         const G4String& name, const G4Transform3D& t,
                         bool checkOverlaps) {
  return new G4PVPlacement(t, lv, name, mother, false, 0, checkOverlaps);
}

}  // namespace scene
