class Node:
    def __init__(self, number: int, hardwares: list,  
                 static_percentage: float, base_stations: list) -> None:
        self.number = number
        self.hardwares = hardwares
        self.base_stations = base_stations
        self.static_percentage = static_percentage

        self.hardwares_key_to_id = {}
        for idx, value in enumerate(self.get_hardware_keys()):
            self.hardwares_key_to_id[value] = self.hardwares[idx]
        
        self.base_stations_key_to_id = {}
        for idx, value in enumerate(self.get_base_station_keys()):
            self.base_stations_key_to_id[value] = self.base_stations[idx]
    
    def has_base_station(self) -> bool:
        if len(self.base_stations) > 0:
            return True
        return False
    
    def has_hardware(self) -> bool:
        if len(self.hardwares) > 0:
            return True
        return False

    def get_hardware_keys(self) -> list:
        return ['node{}_hw{}'.format(self.number, idx) for idx in range(1, len(self.hardwares)+1)]
    
    def get_base_station_keys(self) -> list:
        return ['node{}_bs{}'.format(self.number, idx) for idx in range(1, len(self.base_stations)+1)]

    def get_hardware_type_identifiers(self) -> list:
        return self.hardwares

    def get_base_station_identifiers(self) -> int:
        return self.base_stations

    def get_hardware_identifier(self, key: str) -> int:
        return self.hardwares_key_to_id[key]
    
    def get_base_station_identifier(self, key: str) -> int:
        return self.base_stations_key_to_id[key]

class BaseStation:
    def __init__(self, num_antennas: int, num_subcarriers: int, num_used_subcarriers: int,
                 sampling_frequency: float, ofdm_symbol_duration: float, tau_c: int,
                 tau_p: int, bit_quantization: int, spectral_efficiency: float) -> None:
        self.num_antennas = num_antennas
        self.num_subcarriers = num_subcarriers
        self.num_used_subcarriers = num_used_subcarriers
        self.sampling_frequency = sampling_frequency
        self.ofdm_symbol_duration = ofdm_symbol_duration
        self.tau_c = tau_c
        self.tau_p = tau_p
        self.tau_d = self.tau_c - self.tau_p
        self.bit_quantization = bit_quantization
        self.spectral_efficiency = spectral_efficiency

    

class Hardware:
    def __init__(self, cpu: int, power_consumption: float, gops_capacity: float) -> None:
        self.num_cpu_cores = cpu
        self.power_consumption = power_consumption
        self.gops_capacity = gops_capacity