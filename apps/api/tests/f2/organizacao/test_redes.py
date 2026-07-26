"""T3 -- allowlist CIDR: IPv4 e IPv6, faixa inativa ignorada, familia
incompativel nunca "contem" (IPv4 nunca cai em rede IPv6 e vice-versa).
"""

from __future__ import annotations

from app.organizacao.redes import FaixaPermitida, cidr_valido, ip_autorizado, ip_valido


class TestIpAutorizado:
    def test_ipv4_dentro_da_faixa_e_autorizado(self) -> None:
        faixas = [FaixaPermitida(cidr="200.150.10.0/24")]
        assert ip_autorizado(faixas, "200.150.10.42") is True

    def test_ipv4_fora_da_faixa_e_recusado(self) -> None:
        faixas = [FaixaPermitida(cidr="200.150.10.0/24")]
        assert ip_autorizado(faixas, "200.150.11.1") is False

    def test_ipv6_dentro_da_faixa_e_autorizado(self) -> None:
        faixas = [FaixaPermitida(cidr="2001:db8::/32")]
        assert ip_autorizado(faixas, "2001:db8:1234:5678::1") is True

    def test_ipv6_fora_da_faixa_e_recusado(self) -> None:
        faixas = [FaixaPermitida(cidr="2001:db8::/32")]
        assert ip_autorizado(faixas, "2001:db9::1") is False

    def test_faixa_inativa_e_ignorada(self) -> None:
        faixas = [FaixaPermitida(cidr="200.150.10.0/24", ativo=False)]
        assert ip_autorizado(faixas, "200.150.10.42") is False

    def test_ipv4_nunca_cai_em_faixa_ipv6(self) -> None:
        faixas = [FaixaPermitida(cidr="::/0")]
        assert ip_autorizado(faixas, "8.8.8.8") is False

    def test_multiplas_faixas_qualquer_uma_autoriza(self) -> None:
        faixas = [
            FaixaPermitida(cidr="10.0.0.0/8"),
            FaixaPermitida(cidr="2001:db8::/32"),
        ]
        assert ip_autorizado(faixas, "10.5.5.5") is True
        assert ip_autorizado(faixas, "2001:db8::1") is True
        assert ip_autorizado(faixas, "192.168.1.1") is False

    def test_lista_vazia_nunca_autoriza(self) -> None:
        assert ip_autorizado([], "1.2.3.4") is False


class TestValidacaoDeFormato:
    def test_cidr_valido_ipv4(self) -> None:
        assert cidr_valido("200.150.10.0/24") is True

    def test_cidr_valido_ipv6(self) -> None:
        assert cidr_valido("2001:db8::/32") is True

    def test_cidr_invalido(self) -> None:
        assert cidr_valido("nao-e-um-cidr") is False
        assert cidr_valido("999.999.999.999/24") is False

    def test_ip_valido(self) -> None:
        assert ip_valido("192.168.0.1") is True
        assert ip_valido("::1") is True
        assert ip_valido("nao-e-ip") is False
