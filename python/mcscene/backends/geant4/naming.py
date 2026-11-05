"""Имена объёмов Geant4 и C++ функций — правила цели geant4.

У каждой цели свои правила имён: у Geant4 подходит id как есть, у FLUKA имена
не длиннее 8 символов, у MCNP вместо имён номера. Поэтому это проход цели, а не общий.

id из JSON (^[A-Za-z_][A-Za-z0-9_-]*$) годится как имя объёма Geant4 как есть.
Для имени C++ функции BuildBody_<id> дефис заменяется на подчёркивание.

  - Если два id после замены совпали, второе имя получает суффикс _2 (_3, ...) -> I401.
  - "world" занято под мир: тело с id "world" получает объём "world_body" -> I401.

Кто первый в массиве bodies, тот сохраняет простое имя: результат детерминирован.

Пространство имён C++ для классов сцены — по имени сцены (cpp_namespace): так код сцены
не столкнётся с классами в проекте физика (там почти всегда свой DetectorConstruction)
и с другой сценой в той же программе.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ...diagnostics import Diagnostics
from ...passes import Pass

WORLD = "world"
RESERVED = frozenset({WORLD})

# Слова, которые нельзя взять именем пространства имён: ключевые слова C++20 и имена,
# которые уже заняты в сгенерированном проекте (std, библиотека g4scene, стенд expected).
CPP_RESERVED = frozenset('''
alignas alignof and and_eq asm auto bitand bitor bool break case catch char char8_t char16_t
char32_t class compl concept const consteval constexpr constinit const_cast continue co_await
co_return co_yield decltype default delete do double dynamic_cast else enum explicit export
extern false float for friend goto if inline int long mutable namespace new noexcept not not_eq
nullptr operator or or_eq private protected public register reinterpret_cast requires return
short signed sizeof static static_assert static_cast struct switch template this thread_local
throw true try typedef typeid typename union unsigned using virtual void volatile wchar_t while
xor xor_eq std g4scene expected
'''.split())


@dataclass(frozen=True)
class BodyNames:
    id: str          # id из JSON
    volume: str      # имя solid / логического / физического объёма в Geant4
    func: str        # имя C++ функции, которая строит тело


class Geant4Naming(Pass):
    """Сцена -> {id тела: BodyNames}; плюс имя пространства имён C++ для сцены."""

    @staticmethod
    def cpp_namespace(scene_name: str) -> str:
        """Имя сцены -> имя namespace: rotation_trap -> rotation_trap, 02_box -> scene_02_box.

        Имя C++ не может начинаться с цифры, двойное подчёркивание и подчёркивание в начале
        зарезервированы за компилятором, ключевые слова и занятые имена (CPP_RESERVED) брать
        нельзя, а имя на G4 столкнулось бы с классами Geant4. В этих случаях — приставка scene_.
        """
        name = re.sub(r"[^A-Za-z0-9_]", "_", scene_name)
        name = re.sub(r"_+", "_", name).strip("_") or "scene"
        if name[0].isdigit() or name in CPP_RESERVED or name.startswith("G4"):
            name = "scene_" + name
        return name

    def run(self, scene, diags: Diagnostics) -> dict[str, BodyNames]:
        ids = [b.id for b in scene.bodies]

        taken = set(RESERVED) | {i for i in ids if i not in RESERVED}
        volumes: dict[str, str] = {}
        for i in ids:
            if i in RESERVED:
                v = _unique(i + "_body", taken)
                taken.add(v)
                diags.info("I401", "bodies/%s" % i,
                           "имя %r занято под мир, объём тела назван %r" % (i, v), body_id=i)
            else:
                v = i
            volumes[i] = v

        used: set[str] = set()
        names: dict[str, BodyNames] = {}
        for i in ids:
            base = "BuildBody_" + volumes[i].replace("-", "_")
            f = _unique(base, used)
            used.add(f)
            if f != base:
                diags.info("I401", "bodies/%s" % i,
                           "имя функции %s уже занято другим телом, взято %s" % (base, f), body_id=i)
            names[i] = BodyNames(i, volumes[i], f)
        return names


def _unique(base: str, taken: set[str]) -> str:
    if base not in taken:
        return base
    n = 2
    while "%s_%d" % (base, n) in taken:
        n += 1
    return "%s_%d" % (base, n)
