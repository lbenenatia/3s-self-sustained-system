"""Firmas Ed25519 en Python puro (implementación de referencia del RFC 8032, sección 6).

Discord firma cada pedido que le manda a 3S; verificar esa firma es lo que impide que cualquiera
se haga pasar por Discord. Se usa la versión de referencia (sin dependencias) para que la función
en Vercel no tenga que instalar nada. Es lenta para criptografía masiva, pero verificar un pedido
tarda unas decenas de milisegundos. `firmar` solo se usa en las pruebas.
"""
import hashlib

p = 2 ** 255 - 19
q = 2 ** 252 + 27742317777372353535851937790883648493
d = -121665 * pow(121666, p - 2, p) % p
_SQRT_M1 = pow(2, (p - 1) // 4, p)


def _sha512_modq(s: bytes) -> int:
    return int.from_bytes(hashlib.sha512(s).digest(), "little") % q


def _sumar(P, Q):
    A = (P[1] - P[0]) * (Q[1] - Q[0]) % p
    B = (P[1] + P[0]) * (Q[1] + Q[0]) % p
    C = 2 * P[3] * Q[3] * d % p
    D = 2 * P[2] * Q[2] % p
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % p, G * H % p, F * G % p, E * H % p)


def _multiplicar(s: int, P):
    Q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            Q = _sumar(Q, P)
        P = _sumar(P, P)
        s >>= 1
    return Q


def _iguales(P, Q):
    return (P[0] * Q[2] - Q[0] * P[2]) % p == 0 and (P[1] * Q[2] - Q[1] * P[2]) % p == 0


def _recuperar_x(y, signo):
    if y >= p:
        return None
    x2 = (y * y - 1) * pow(d * y * y + 1, p - 2, p) % p
    if x2 == 0:
        return None if signo else 0
    x = pow(x2, (p + 3) // 8, p)
    if (x * x - x2) % p != 0:
        x = x * _SQRT_M1 % p
    if (x * x - x2) % p != 0:
        return None
    if (x & 1) != signo:
        x = p - x
    return x


_GY = 4 * pow(5, p - 2, p) % p
_GX = _recuperar_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % p)


def _comprimir(P) -> bytes:
    zinv = pow(P[2], p - 2, p)
    x, y = P[0] * zinv % p, P[1] * zinv % p
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _descomprimir(s: bytes):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    signo = y >> 255
    y &= (1 << 255) - 1
    x = _recuperar_x(y, signo)
    return None if x is None else (x, y, 1, x * y % p)


def _expandir(secreto: bytes):
    h = hashlib.sha512(secreto).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def publica(secreto: bytes) -> bytes:
    return _comprimir(_multiplicar(_expandir(secreto)[0], _G))


def firmar(secreto: bytes, mensaje: bytes) -> bytes:
    a, prefijo = _expandir(secreto)
    A = _comprimir(_multiplicar(a, _G))
    r = _sha512_modq(prefijo + mensaje)
    Rs = _comprimir(_multiplicar(r, _G))
    s = (r + _sha512_modq(Rs + A + mensaje) * a) % q
    return Rs + int.to_bytes(s, 32, "little")


def verificar(clave_publica: bytes, mensaje: bytes, firma: bytes) -> bool:
    if len(clave_publica) != 32 or len(firma) != 64:
        return False
    A = _descomprimir(clave_publica)
    R = _descomprimir(firma[:32])
    if A is None or R is None:
        return False
    s = int.from_bytes(firma[32:], "little")
    if s >= q:
        return False
    h = _sha512_modq(firma[:32] + clave_publica + mensaje)
    return _iguales(_multiplicar(s, _G), _sumar(R, _multiplicar(h, A)))
