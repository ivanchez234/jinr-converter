"""Повороты и жёсткие преобразования — объекты-значения.

Rotation — сам поворот (матрица 3×3 по строкам, столбцы = оси тела в системе родителя).
Не путать с model.Rotation: то — запись поворота в JSON (identity / matrix_active /
euler_xyz_extrinsic_deg), а Rotation.from_contract() превращает её в поворот.

Соглашения контракта (КОНТРАКТ.md, раздел 3):
  matrix_active           — матрица по строкам, столбцы = оси тела в системе родителя;
  euler_xyz_extrinsic_deg — повороты вокруг неподвижных осей: сначала X на a,
                            потом Y на b, потом Z на c, то есть R = Rz(c)·Ry(b)·Rx(a).
В обоих случаях точка тела p попадает в систему родителя как R·p + t.

Матрица из JSON доводится до точно ортонормированной (orthonormalized): validate.py
пропускает отклонение до 1e-6 (например, если элементы записаны с округлением),
а g4scene в C++ проверяет поворот с допуском 1e-9 и иначе остановит Geant4.

Объекты неизменяемые: каждая операция возвращает новый объект.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

Vec3 = tuple[float, float, float]
Mat3 = tuple[Vec3, Vec3, Vec3]

IDENTITY: Mat3 = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
ZERO: Vec3 = (0.0, 0.0, 0.0)


@dataclass(frozen=True)
class Rotation:
    """Поворот как матрица 3×3 по строкам."""
    matrix: Mat3 = IDENTITY

    # --- откуда берётся --------------------------------------------------------
    @classmethod
    def from_contract(cls, rot) -> "Rotation":
        """Запись поворота из Scene IR (RotIdentity / RotMatrix / RotEuler или None)."""
        if rot is None or rot.convention == "identity":
            return cls()
        if rot.convention == "matrix_active":
            return cls.of(rot.matrix).orthonormalized().snapped()
        if rot.convention == "euler_xyz_extrinsic_deg":
            return cls.euler_xyz_deg(*rot.angles)
        raise ValueError("неизвестное соглашение о повороте: %r" % rot.convention)

    @classmethod
    def of(cls, m: Sequence[Sequence[float]]) -> "Rotation":
        """Из любых трёх строк по три числа."""
        return cls(tuple(tuple(float(x) for x in row) for row in m))  # type: ignore[arg-type]

    @classmethod
    def euler_xyz_deg(cls, a: float, b: float, c: float) -> "Rotation":
        """Сначала X на a, потом Y на b, потом Z на c (градусы): R = Rz·Ry·Rx."""
        a, b, c = (math.radians(x) for x in (a, b, c))
        return (cls.about_z(c) @ (cls.about_y(b) @ cls.about_x(a))).snapped()

    @classmethod
    def about_x(cls, a: float) -> "Rotation":
        c, s = math.cos(a), math.sin(a)
        return cls(((1.0, 0.0, 0.0), (0.0, c, -s), (0.0, s, c)))

    @classmethod
    def about_y(cls, a: float) -> "Rotation":
        c, s = math.cos(a), math.sin(a)
        return cls(((c, 0.0, s), (0.0, 1.0, 0.0), (-s, 0.0, c)))

    @classmethod
    def about_z(cls, a: float) -> "Rotation":
        c, s = math.cos(a), math.sin(a)
        return cls(((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0)))

    # --- что умеет -------------------------------------------------------------
    def __matmul__(self, other: "Rotation") -> "Rotation":
        """Композиция: (self @ other).apply(p) == self.apply(other.apply(p))."""
        a, b = self.matrix, other.matrix
        return Rotation(tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3))
                              for i in range(3)))  # type: ignore[arg-type]

    def apply(self, v: Sequence[float]) -> Vec3:
        m = self.matrix
        return (m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
                m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
                m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2])

    def transposed(self) -> "Rotation":
        m = self.matrix
        return Rotation(tuple(tuple(m[j][i] for j in range(3)) for i in range(3)))  # type: ignore[arg-type]

    @property
    def det(self) -> float:
        m = self.matrix
        return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
                - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))

    @property
    def deviation(self) -> float:
        """max |(M·Mᵀ)_ij − δ_ij| — насколько матрица не ортонормирована."""
        mmt = (self @ self.transposed()).matrix
        return max(abs(mmt[i][j] - (1.0 if i == j else 0.0)) for i in range(3) for j in range(3))

    def orthonormalized(self, max_iter: int = 20) -> "Rotation":
        """Ближайшая ортонормированная матрица (итерация Бьёрка: R <- R·(3I − RᵀR)/2).

        Для почти ортонормированной матрицы сходится за 2–3 шага, точную не меняет.
        """
        r = self
        for _ in range(max_iter):
            if r.deviation < 1e-15:
                break
            rtr = (r.transposed() @ r).matrix
            k = Rotation(tuple(tuple((3.0 if i == j else 0.0) - rtr[i][j] for j in range(3))
                               for i in range(3)))  # type: ignore[arg-type]
            r = Rotation(tuple(tuple(x / 2 for x in row) for row in (r @ k).matrix))  # type: ignore[arg-type]
        return r

    def snapped(self, eps: float = 1e-12) -> "Rotation":
        """Без шума вида 6.1e-17, 0.9999999999999998 и -0.0 — для читаемого кода."""
        def one(x: float) -> float:
            if abs(x) < eps:
                return 0.0
            if abs(x - 1.0) < eps:
                return 1.0
            if abs(x + 1.0) < eps:
                return -1.0
            return float(x)
        return Rotation(tuple(tuple(one(x) for x in row) for row in self.matrix))  # type: ignore[arg-type]

    @property
    def is_identity(self) -> bool:
        return self.matrix == IDENTITY

    @property
    def is_axis_permutation(self) -> bool:
        """Поворот, который только переставляет оси (в каждой строке одно ±1)."""
        return all(sorted(abs(x) for x in row) == [0.0, 0.0, 1.0] for row in self.matrix)


@dataclass(frozen=True)
class Rigid:
    """Жёсткое преобразование p -> R·p + t (поворот, потом сдвиг)."""
    rotation: Rotation = field(default_factory=Rotation)
    t: Vec3 = ZERO

    @classmethod
    def from_transform(cls, tf) -> "Rigid":
        """transform из Scene IR (или None) -> Rigid."""
        if tf is None:
            return cls()
        return cls(Rotation.from_contract(tf.rotation), tuple(float(x) for x in tf.translation))

    def apply(self, p: Sequence[float]) -> Vec3:
        q = self.rotation.apply(p)
        return (q[0] + self.t[0], q[1] + self.t[1], q[2] + self.t[2])

    def then_child(self, child: "Rigid") -> "Rigid":
        """Преобразование «ребёнок -> мир», если self — «родитель -> мир».

        p_мир = R_род·(R_реб·p + t_реб) + t_род.
        """
        return Rigid(self.rotation @ child.rotation, self.apply(child.t))
