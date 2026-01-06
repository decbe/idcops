class PowerConverter:
    """电力单位转换工具"""

    @staticmethod
    def kw_to_ampere(kw: float, voltage: float = 220, power_factor: float = 1) -> float:
        """千瓦转换为安培

        Args:
            kw: 功率，单位千瓦
            voltage: 电压，默认220V
            power_factor: 功率因数，默认1

        公式: I(A) = P(W) / (V × PF × √3)  # 三相
             I(A) = P(W) / (V × PF)        # 单相

        """
        watts = kw * 1000  # 转换为瓦特

        # 三相交流
        if voltage > 220:  # 一般380V为三相
            ampere = watts / (voltage * power_factor * 1.732)  # √3 ≈ 1.732
        # 单相交流
        else:
            ampere = watts / (voltage * power_factor)

        return round(ampere, 2)

    @staticmethod
    def ampere_to_kw(
        ampere: float, voltage: float = 220, power_factor: float = 1
    ) -> float:
        """安培转换为千瓦

        Args:
            ampere: 电流，单位安培
            voltage: 电压，默认220V
            power_factor: 功率因数，默认1

        公式: P(W) = I(A) × V × PF × √3  # 三相
             P(W) = I(A) × V × PF        # 单相

        """
        # 三相交流
        if voltage > 220:
            watts = ampere * voltage * power_factor * 1.732
        # 单相交流
        else:
            watts = ampere * voltage * power_factor

        return round(watts / 1000, 2)  # 转换为千瓦

    @staticmethod
    def get_power_factor(kw: float, kva: float) -> float:
        """计算功率因数

        Args:
            kw: 有功功率，单位千瓦
            kva: 视在功率，单位千伏安

        公式: PF = P(kW) / S(kVA)

        """
        return round(kw / kva, 2) if kva else 0
