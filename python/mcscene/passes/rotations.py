"""Повороты: любая запись поворота из контракта -> матрица 3×3.

Соглашения контракта (КОНТРАКТ.md, раздел 3):
  matrix_active           — матрица по строкам, столбцы = оси тела в системе родителя;
  euler_xyz_extrinsic_deg — повороты вокруг неподвижных осей: сначала X на a,
                            потом Y на b, потом Z на c, то есть R = Rz(c)·Ry(b)·Rx(a).
В обоих случаях точка тела p попадает в систему родителя как R·p + t.

Матрица из JSON доводится до точно ортонормированной (orthonormalize): validate.py
пропускает отклонение до 1e-6 (например, если элементы записаны с округлением),
а g4scene в C++ проверяет поворот с допуском 1e-9 и иначе остановит Geant4.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

Vec3 = tuple[float, float, float]
Mat3 = tuple[Vec3, Vec3, Vec3]

IDENTITY: Mat3 = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
ZERO: Vec3 = (0.0, 0.0, 0.0)


def to_matrix(rot) -> Mat3:
    """Поворот из Scene IR (RotIdentity / RotMatrix / RotEuler) -> матрица 3×3 по строкам."""
    if rot is None or rot.convention == "identity":
        return IDENTITY
    if rot.convention == "matrix_active":
        return snap(orthonormalize(rot.matrix))
    if rot.convention == "euler_xyz_extrinsic_deg":
        a, b, c = (math.radians(x) for x in rot.angles)
        return snap(mul(rz(c), mul(ry(b), rx(a))))
    raise ValueError("неизвестное соглашение о повороте: %r" % rot.convention)


def snap(m: Sequence[Sequence[float]], eps: float = 1e-12) -> Mat3:
    """Убирает шум вида 6.1e-17, 0.9999999999999998 и -0.0 — для читаемого кода."""
    def one(x: float) -> float:
        if abs(x) < eps:
            return 0.0
        if abs(x - 1.0) < eps:
            return 1.0
        if abs(x + 1.0) < eps:
            return -1.0
        return float(x)
    return tuple(tuple(one(x) for x in row) for row in m)  # type: ignore[return-value]


# --- элементарные повороты (углы в радианах) ---
def rx(a: float) -> Mat3:
    c, s = math.cos(a), math.sin(a)
    return ((1.0, 0.0, 0.0), (0.0, c, -s), (0.0, s, c))


def ry(a: float) -> Mat3:
    c, s = math.cos(a), math.sin(a)
    return ((c, 0.0, s), (0.0, 1.0, 0.0), (-s, 0.0, c))


def rz(a: float) -> Mat3:
    c, s = math.cos(a), math.sin(a)
    return ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))


# --- линейная алгебра 3×3 ---
def mul(a: Mat3, b: Mat3) -> Mat3:
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3))
                 for i in range(3))  # type: ignore[return-value]


def apply(m: Mat3, v: Sequence[float]) -> Vec3:
    return (m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
            m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
            m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2])


def transpose(m: Mat3) -> Mat3:
    return tuple(tuple(m[j][i] for j in range(3)) for i in range(3))  # type: ignore[return-value]


def det(m: Mat3) -> float:
    return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))


def deviation(m: Mat3) -> float:
    """max |(M·Mᵀ)_ij − δ_ij| — насколько матрица не ортонормирована."""
    mmt = mul(m, transpose(m))
    return max(abs(mmt[i][j] - (1.0 if i == j else 0.0)) for i in range(3) for j in range(3))


def orthonormalize(m: Sequence[Sequence[float]], max_iter: int = 20) -> Mat3:
    """Ближайшая ортонормированная матрица (итерация Бьёрка: R <- R·(3I − RᵀR)/2).

    Для почти ортонормированной матрицы сходится за 2–3 шага, точную не меняет.
    """
    r: Mat3 = tuple(tuple(float(x) for x in row) for row in m)  # type: ignore[assignment]
    for _ in range(max_iter):
        if deviation(r) < 1e-15:
            break
        rtr = mul(transpose(r), r)
        k = tuple(tuple((3.0 if i == j else 0.0) - rtr[i][j] for j in range(3)) for i in range(3))
        r = tuple(tuple(x / 2 for x in row) for row in mul(r, k))  # type: ignore[arg-type]
    return r


def is_axis_permutation(m: Mat3) -> bool:
    """Поворот, который только переставляет оси (в каждой строке одно ±1)."""
    return all(sorted(abs(x) for x in row) == [0.0, 0.0, 1.0] for row in m)


@dataclass(frozen=True)
class Rigid:
    """Жёсткое преобразование p -> R·p + t (поворот, потом сдвиг)."""
    r: Mat3 = IDENTITY
    t: Vec3 = ZERO

    @classmethod
    def from_transform(cls, tf) -> "Rigid":
        """transform из Scene IR (или None) -> Rigid."""
        if tf is None:
            return cls()
        return cls(to_matrix(tf.rotation), tuple(float(x) for x in tf.translation))

    def apply(self, p: Sequence[float]) -> Vec3:
        q = apply(self.r, p)
        return (q[0] + self.t[0], q[1] + self.t[1], q[2] + self.t[2])

    def then_child(self, child: "Rigid") -> "Rigid":
        """Преобразование «ребёнок -> мир», если self — «родитель -> мир».

        p_мир = R_род·(R_реб·p + t_реб) + t_род.
        """
        return Rigid(mul(self.r, child.r), self.apply(child.t))
