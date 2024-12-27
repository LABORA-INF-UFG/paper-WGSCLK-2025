import math

from docplex.mp.constr import AbstractConstraint
from docplex.mp.linear import LinearExpr, ZeroExpr
from docplex.mp.model import Model

import core.drc as package_drc
from core.topology import *

CR_MODE_CALC = "calc"
CR_MODE_HP = "hp"
CR_MODE_HL = "hl"
SERVICE_URLLC = "urllc"
SERVICE_1080P = "1080"
SERVICE_1440P = "1440"
SERVICE_2160P = "2160"

class EEPRANModel:
    def __init__(self, model: Model, centralization_constraint: AbstractConstraint,
                 ran_power_expr: LinearExpr, net_power_expr: LinearExpr, mig_power_expr: LinearExpr,
                 link_usage_exprs: dict[str, LinearExpr], link_power_exprs: dict[str, LinearExpr],
                 hw_usage_exprs: dict[str, LinearExpr], hw_capacities: dict[str, int],
                 node_vnf_gops: dict[str, dict[str, float]]) -> None:
        self.model = model
        self.centralizationContraint = centralization_constraint
        self.nodeVnfGops = node_vnf_gops
        self.ranPowerExpr = ran_power_expr
        self.netPowerExpr = net_power_expr
        self.migPowerExpr = mig_power_expr
        self.linkUsageExprs = link_usage_exprs
        self.linkPowerExprs = link_power_exprs
        self.hwUsageExprs = hw_usage_exprs
        self.hwCapacities = hw_capacities


def build_eepran_model(topo: Topology, timestamp: int = -1, centralization_cap: int = 0, service: str = SERVICE_URLLC,
                       cr_mode: str = CR_MODE_CALC, actual_deployment: Deployment = None) -> EEPRANModel:
    model = Model(name='EEPRAN Problem', log_output=True)
    model.parameters.mip.tolerances.mipgap = 1e-5

    logging.info('Model Creation Time:')

    # -----------
    # Define Data
    # -----------

    data_defining_start = time.time()

    splits = package_drc.get_drc_list_urllc()
    drc_dict = {drc.identifier: drc for drc in splits}

    splits_embb = package_drc.get_drc_list_embb()
    drc_dict_embb = {drc.identifier: drc for drc in splits_embb}

    vnf_mem_usage = {
        "f2": 1795.00,
        "f3": 121.04,
        "f4": 121.04,
        "f5": 86.46,
        "f6": 86.46,
        "f7": 410.00,
        "f8": 410.00
    }

    vnf_mig_cost = {key: (0.512 * 3 * value + 20.165) for key, value in vnf_mem_usage.items()}
    virtual_network_functions = ['f2', 'f3', 'f4', 'f5', 'f6', 'f7', 'f8']

    maximum_centralization = len(virtual_network_functions) * len(topo.get_base_station_keys())

    integer_feasibility_tolerance = 1 / maximum_centralization

    throughput_urllc = 1024000
    throughput_1080p = 12000000
    throughput_1440p = 24000000
    throughput_2160p = 53000000

    throughput = throughput_urllc

    if service == SERVICE_1080P:
        throughput = throughput_1080p
        splits = splits_embb
        drc_dict = drc_dict_embb
    elif service == SERVICE_1440P:
        throughput = throughput_1440p
        splits = splits_embb
        drc_dict = drc_dict_embb
    elif service == SERVICE_2160P:
        throughput = throughput_2160p
        splits = splits_embb
        drc_dict = drc_dict_embb

    bs_users = {}
    if timestamp == -1:
        bs_users = {bs_key: 1 for bs_key in topo.get_base_station_keys()}
    else:
        bs_users = topo.get_load_at(timestamp)

    if actual_deployment is None:
        actual_deployment = Deployment(topo.get_base_station_keys(), splits, topo.get_routes())

    data_defining_end = time.time()
    logging.info('    Data Definition: {}s'.format(data_defining_end - data_defining_start))

    # --------------------------
    # Define Decision Variable X
    # --------------------------

    var_definition_start = time.time()

    # list with keys for decision variables
    DecisionVariableKey = namedtuple('DecisionVariableKey', ['route_id', 'drc_id', 'bs_key'])
    decision_var_keys = [
        DecisionVariableKey(route.identifier, drc.identifier, bs_key)
        for route in topo.get_routes()
        for drc in splits
        for bs_key in topo.get_base_station_keys()
        if route.is_destination(bs_key)
           and drc.num_needed_nodes() == route.qty_nodes()
           and route.delay_backhaul <= drc.delay_bh
           and route.delay_midhaul <= drc.delay_mh
           and route.delay_fronthaul <= drc.delay_fh
    ]

    splits7_2 = [1, 2, 4, 6, 9]
    splits6 = [62]
    decision_var_keys = []
    for route in topo.get_routes():
        for drc in splits:
            for bs_key in topo.get_base_station_keys():

                if not route.is_destination(bs_key):
                    continue
                if drc.num_needed_nodes() != route.qty_nodes():
                    continue

                buffer_size = 0
                if drc.identifier in splits6:
                    buffer_size = 2
                elif drc.identifier in splits7_2:
                    buffer_size = 2

                packet_size = 12368.0

                fronthaul_delay = route.delay_fronthaul  # Optical Propagation Delay (5 us/km)
                for link_key in route.fronthaul:
                    link = topo.get_link(str(link_key))
                    fronthaul_delay += 0.005  # Switch Electrical Processing Delay (0.005 ms)
                    fronthaul_delay += packet_size / (link.port_capacity * 10 ** 9) * 10**3  # Transmission Delay
                    fronthaul_delay += buffer_size * packet_size / (link.port_capacity * 10 ** 9) * 10**3  # Buffer Delay

                midhaul_delay = route.delay_midhaul  # Optical Propagation Delay (5 us/km)
                for link_key in route.midhaul:
                    link = topo.get_link(str(link_key))
                    midhaul_delay += 0.005  # Switch Electrical Processing Delay (0.005 ms)
                    midhaul_delay += packet_size / (link.port_capacity * 10 ** 9) * 10**3  # Transmission Delay
                    midhaul_delay += buffer_size * packet_size / (link.port_capacity * 10 ** 9) * 10**3   # Buffer Delay

                backhaul_delay = route.delay_backhaul  # Optical Propagation Delay (5 us/km)
                for link_key in route.backhaul:
                    link = topo.get_link(str(link_key))
                    backhaul_delay += 0.005  # Switch Electrical Processing Delay (0.005 ms)
                    backhaul_delay += packet_size / (link.port_capacity * 10 ** 9) * 10**3   # Transmission Delay
                    backhaul_delay += buffer_size * packet_size / (link.port_capacity * 10 ** 9) * 10**3  # Buffer Delay (300us)

                if fronthaul_delay > drc.delay_fh or midhaul_delay > drc.delay_mh or backhaul_delay > drc.delay_bh:
                    continue

                decision_var_keys.append(DecisionVariableKey(route.identifier, drc.identifier, bs_key))

    # for key in decision_var_keys:
    #     print(key, " -> ", topo.get_route(key.route_id).sequence)

    # list with keys for ceil variables in psi_2
    CeilVariableKey = namedtuple('CeilVariableKey', ['node_key', 'function_key'])
    ceil_var_keys = [CeilVariableKey(node_key, function_key)
                     for node_key in topo.get_node_keys()
                     for function_key in virtual_network_functions
                     if topo.get_node(node_key).has_hardware()]

    model.x = model.binary_var_dict(
        keys=decision_var_keys,
        name=lambda vk: 'x_path{}_drc{}_{}'.format(vk.route_id, vk.drc_id, vk.bs_key)
    )
    model.y = model.integer_var_dict(keys=topo.get_hardware_keys(), name='y')
    model.z = model.integer_var_dict(keys=ceil_var_keys, name='z')

    # model.w = model.integer_var_dict(keys=topo.get_links(), name='w')

    var_definition_end = time.time()
    logging.info('    Variables Definition: {}s'.format(var_definition_end - var_definition_start))

    # -------------------------
    # Define Objective Function
    # -------------------------

    objective_function_start = time.time()

    ran_power_consumption = model.linear_expr()
    base_station_power_expression = model.linear_expr()
    dynamic_power_expression = model.linear_expr()
    static_power_consumptions = {}
    link_usage_expressions = {}
    node_vnf_gops: dict[str, dict[str, float]] = {}
    psi_1 = {}
    key_link_association = {}
    hardware_processing_expressions: dict[str, LinearExpr] = {}

    for key in decision_var_keys:
        route = topo.get_route(key.route_id)

        # ---------- vRAN Consumption ----------
        for function in virtual_network_functions:
            hw = None
            node = None
            hw_key = None

            if route.has_backhaul() and function in drc_dict[key.drc_id].fs_cu:
                node_key = route.get_backhaul_node_key()
                hw_key = route.get_backhaul_hardware_key()

                hw = topo.get_hardware_by_key(hw_key)
                node = topo.get_node(node_key)

            elif route.has_midhaul() and function in drc_dict[key.drc_id].fs_du:
                node_key = route.get_midhaul_node_key()
                hw_key = route.get_midhaul_hardware_key()

                hw = topo.get_hardware_by_key(hw_key)
                node = topo.get_node(node_key)

            elif function in drc_dict[key.drc_id].fs_ru:
                node_key = route.get_fronthaul_node_key()
                hw_key = route.get_fronthaul_hardware_key()

                hw = topo.get_hardware_by_key(hw_key)
                node = topo.get_node(node_key)

            if hw is None or node is None or hw_key is None:
                continue

            if route.get_target_base_station() not in node_vnf_gops.keys():
                bs = topo.get_base_station(1)

                # c_filter = 40 * bs.num_antennas * bs.sampling_frequency / 10**9
                # c_dft = (8 * bs.num_antennas * bs.num_subcarriers * math.log2(bs.num_subcarriers)) / (bs.ofdm_symbol_duration * 10**9)

                c_precoding = (bs.num_used_subcarriers / (bs.ofdm_symbol_duration * bs.tau_c * 10 ** 9)) * \
                              (8 * bs.num_antennas * bs.tau_p ** 2 + 8 * bs.num_antennas ** 2 * (
                                      bs.tau_p + bs_users[key.bs_key])) + \
                              (bs.num_used_subcarriers * bs.tau_d / (bs.ofdm_symbol_duration * bs.tau_c * 10 ** 9)) * \
                              (8 * bs.num_antennas * bs_users[key.bs_key]) + \
                              (bs.num_used_subcarriers / (bs.ofdm_symbol_duration * bs.tau_c * 10 ** 9)) * \
                              (8 * bs.num_antennas * bs_users[key.bs_key]) + \
                              (bs.num_used_subcarriers / (bs.ofdm_symbol_duration * bs.tau_c * 10 ** 9)) * \
                              ((4 * bs.num_antennas ** 2 + 4 * bs.num_antennas) * bs.tau_p + 8 * bs.num_antennas ** 2 *
                               bs_users[key.bs_key] + 8 * (bs.num_antennas ** 3 - bs.num_antennas) / 3)

                c_modulation = 1.3 * (bs.bit_quantization / 16) ** 1.2 * bs.num_antennas
                c_mapping = 1.3 * (bs.bit_quantization / 16) ** 1.2 * (bs.spectral_efficiency / 6) ** 1.5 * bs_users[
                    key.bs_key]
                c_channel_coding = 1.3 * (bs.bit_quantization / 16) ** 1.2 * (bs.spectral_efficiency / 6) * bs_users[
                    key.bs_key]

                c_control = 2.7 * (bs.bit_quantization / 16) ** 0.2 * math.sqrt(bs.num_antennas)
                c_network = 8.0 * (bs.spectral_efficiency / 6) * bs_users[key.bs_key]

                # low_phy_gops = c_filter + c_dft
                high_phy_gops = c_precoding + c_modulation + c_mapping
                high_layer_gops = c_channel_coding + c_control + c_network

                if cr_mode == CR_MODE_HP:
                    high_layer_gops = high_phy_gops / 0.327 - high_phy_gops
                elif cr_mode == CR_MODE_HL:
                    high_phy_gops = high_layer_gops / 0.673 - high_layer_gops

                node_vnf_gops[route.get_target_base_station()] = {'f2': high_phy_gops,
                                                                  'f3': 0.2 * high_layer_gops,
                                                                  'f4': 0.2 * high_layer_gops,
                                                                  'f5': 0.014 * high_layer_gops,
                                                                  'f6': 0.014 * high_layer_gops,
                                                                  'f7': 0.286 * high_layer_gops,
                                                                  'f8': 0.286 * high_layer_gops,
                                                                  'c_modulation': c_modulation,
                                                                  'c_mapping': c_mapping,
                                                                  'c_channel_coding': c_channel_coding,
                                                                  'c_control': c_control,
                                                                  'c_network': c_network,
                                                                  'high_phy': high_phy_gops,
                                                                  'high_layer': high_layer_gops}

            dynamic_power_consumption = hw.power_consumption * (1 - node.static_percentage)

            dynamic_power_expression.add_term(
                model.x[key],
                (node_vnf_gops[route.get_target_base_station()][
                     function] * dynamic_power_consumption / hw.gops_capacity)
            )

            psi_1.setdefault(hw_key, model.linear_expr()).add_term(
                model.x[key],
                1.0 / maximum_centralization
            )

            hardware_processing_expressions.setdefault(hw_key, model.linear_expr()).add_term(
                model.x[key],
                node_vnf_gops[route.get_target_base_station()][function]
            )

            if hw_key not in static_power_consumptions.keys():
                static_power_consumptions[hw_key] = hw.power_consumption * node.static_percentage

        # ---------- Network Link Usage ----------
        route = topo.get_route(key.route_id)

        links = {'backhaul': [], 'midhaul': [], 'fronthaul': [],
                 'backhaul_load': 0.0, 'midhaul_load': 0.0, 'fronthaul_load': 0.0}

        bandwidth = drc_dict_embb[key.drc_id].bandwidth_bh * throughput * bs_users[key.bs_key] * 10 ** (-9)
        links['backhaul_load'] = bandwidth
        for link_key in route.get_backhaul_links():
            links['backhaul'].append(link_key)
            link_usage_expressions.setdefault(link_key, model.linear_expr()).add_term(
                model.x[key],
                bandwidth
            )

        bandwidth = drc_dict_embb[key.drc_id].bandwidth_mh * throughput * bs_users[key.bs_key] * 10 ** (-9)
        links['midhaul_load'] = bandwidth
        for link_key in route.get_midhaul_links():
            links['midhaul'].append(link_key)
            link_usage_expressions.setdefault(link_key, model.linear_expr()).add_term(
                model.x[key],
                bandwidth
            )

        bandwidth = drc_dict_embb[key.drc_id].bandwidth_fh * throughput * bs_users[key.bs_key] * 10 ** (-9)
        links['fronthaul_load'] = bandwidth
        for link_key in route.get_fronthaul_links():
            links['fronthaul'].append(link_key)
            link_usage_expressions.setdefault(link_key, model.linear_expr()).add_term(
                model.x[key],
                bandwidth
            )

        key_link_association[key] = links

    # ---------- RAN Power Consumption Definition ----------
    ran_power_consumption.add(dynamic_power_expression)
    for hw_key in topo.get_hardware_keys():
        # if hw_key not in psi_1.keys(): 
        #     continue

        # model.add_constraint(model.y[hw_key] - psi_1[hw_key] >= 0.0, 
        #                         'low_ceil_restriction_{}'.format(hw_key))
        # model.add_constraint(model.y[hw_key] - psi_1[hw_key] <= 1.0 - integer_feasibility_tolerance,
        #                         'high_ceil_restriction_{}'.format(hw_key))

        if hw_key not in hardware_processing_expressions.keys():
            continue

        model.add_constraint(model.y[hw_key] - hardware_processing_expressions[hw_key] / topo.get_hardware_by_key(
            hw_key).gops_capacity >= 0.0,
                             'low_ceil_restriction_{}'.format(hw_key))
        model.add_constraint(model.y[hw_key] - hardware_processing_expressions[hw_key] / topo.get_hardware_by_key(
            hw_key).gops_capacity <= 1.0 - integer_feasibility_tolerance,
                             'high_ceil_restriction_{}'.format(hw_key))

        ran_power_consumption.add_term(model.y[hw_key], static_power_consumptions[hw_key])

    ran_power_consumption = ran_power_consumption * 3600

    # ---------- Network Power Consumption Definition ----------
    net_power_consumption = model.linear_expr()
    link_power_expressions = {}
    net_power_costs = {}
    for link_key, expression in link_usage_expressions.items():
        link = topo.get_link(link_key)

        # model.add_constraint(model.w[link_key] >= expression / link.port_capacity, 'ports_usage_lower_bound_link_{}'.format(link_key))
        # model.add_constraint(model.w[link_key] - 1 <= (expression / link.port_capacity) - 10**(-12), 'ports_usage_higher_bound_link_{}'.format(link_key))

        # ----- Link Capacity Constraint -----
        model.add_constraint(expression / link.port_capacity <= link.max_ports,
                             'qty_ports_link_{}'.format(link_key))

        # ----- Network Power Consumption -----
        is_node1_switch = 1 if link.is_node1_switch else 0
        is_node2_switch = 1 if link.is_node2_switch else 0
        net_power_consumption += (
                expression / link.port_capacity * (
                (2 * link.pluggable_transceiver_power_consumption) +
                (link.switch_port_power_consumption * (is_node1_switch + is_node2_switch))
        )
        )

        link_power_expressions[link_key] = (
                expression / link.port_capacity * (
                (2 * link.pluggable_transceiver_power_consumption) +
                (link.switch_port_power_consumption * (is_node1_switch + is_node2_switch))
        )
        )

        net_power_costs[link_key] = (
                (2 * link.pluggable_transceiver_power_consumption) +
                (link.switch_port_power_consumption * (is_node1_switch + is_node2_switch))
        )

    net_power_consumption = net_power_consumption * 3600

    for key in decision_var_keys:
        # print(net_power_costs.keys())

        key_link_association[key]['backhaul_power'] = []
        for link in key_link_association[key]['backhaul']:
            key_link_association[key]['backhaul_power'].append(net_power_costs[link])

        key_link_association[key]['midhaul_power'] = []
        for link in key_link_association[key]['midhaul']:
            key_link_association[key]['midhaul_power'].append(net_power_costs[link])

        key_link_association[key]['fronthaul_power'] = []
        for link in key_link_association[key]['fronthaul']:
            key_link_association[key]['fronthaul_power'].append(net_power_costs[link])

    # ---------- Migration Power Consumption Definition ---------
    mig_function_start = time.time()

    mig_power_consumption = model.linear_expr(name="migration")
    for key in decision_var_keys:
        route = topo.get_route(key.route_id)
        for fs in drc_dict[key.drc_id].fs_cu:
            if fs not in virtual_network_functions:
                continue
            mig_power_consumption += (1 - actual_deployment.IsDeployedIn(key.bs_key, fs,
                                                                         route.get_backhaul_hardware_key())) * model.x[
                                         key] * vnf_mig_cost[fs]
        for fs in drc_dict[key.drc_id].fs_du:
            if fs not in virtual_network_functions:
                continue
            mig_power_consumption += (1 - actual_deployment.IsDeployedIn(key.bs_key, fs,
                                                                         route.get_midhaul_hardware_key())) * model.x[
                                         key] * vnf_mig_cost[fs]
        for fs in drc_dict[key.drc_id].fs_ru:
            if fs not in virtual_network_functions:
                continue
            mig_power_consumption += (1 - actual_deployment.IsDeployedIn(key.bs_key, fs,
                                                                         route.get_fronthaul_hardware_key())) * model.x[
                                         key] * vnf_mig_cost[fs]

    mig_function_end = time.time()
    logging.info('      - Migration Function Definition: {}s'.format(mig_function_end - mig_function_start))

    # --------- Objective Definition ----------

    # model.minimize(ran_power_consumption + net_power_consumption + mig_power_consumption)
    # model.minimize(ran_power_consumption + net_power_consumption)

    objective_function_end = time.time()
    logging.info('    Objective Definition: {}s'.format(objective_function_end - objective_function_start))
    # --------------------------------
    # Define Centralization Constraint
    # --------------------------------

    centralization_function_start = time.time()

    centralization = model.linear_expr()
    vnf_count_expressions = {}
    for key in decision_var_keys:
        route = topo.get_route(key.route_id)

        for function in virtual_network_functions:
            if route.has_backhaul() and function in drc_dict[key.drc_id].fs_cu:
                node_key = route.get_backhaul_node_key()

                vnf_count_expressions.setdefault(CeilVariableKey(node_key, function),
                                                 model.linear_expr()).add(model.x[key])

            elif route.has_midhaul() and function in drc_dict[key.drc_id].fs_du:
                node_key = route.get_midhaul_node_key()

                vnf_count_expressions.setdefault(CeilVariableKey(node_key, function),
                                                 model.linear_expr()).add(model.x[key])

            elif route.has_fronthaul() and function in drc_dict[key.drc_id].fs_ru:
                node_key = route.get_fronthaul_node_key()

                vnf_count_expressions.setdefault(CeilVariableKey(node_key, function),
                                                 model.linear_expr()).add(model.x[key])

    for key in ceil_var_keys:
        if key in vnf_count_expressions.keys():
            expression = vnf_count_expressions[key]
        else:
            expression = 0

        # Psi_2 Ceil Function Restriction
        model.add_constraint(
            model.z[key] - (expression / maximum_centralization) >=
            0.0, 'low_ceil_restriction_{}_{}'.format(key.node_key, key.function_key)
        )
        model.add_constraint(
            model.z[key] - (expression / maximum_centralization) <=
            1.0 - integer_feasibility_tolerance,
            'high_ceil_restriction_{}_{}'.format(key.node_key, key.function_key)
        )

        # centralization is calculated by CR (not by Hardware)
        centralization += model.sum(expression - model.z[key])

    centralization_constraint = model.add_constraint(centralization >= centralization_cap, 'centralization_constraint')

    model.maximize(centralization)

    centralization_function_end = time.time()
    logging.info(
        '    Centralization Definition: {}s'.format(centralization_function_end - centralization_function_start))

    # ------------------------------
    # Define Single Route Constraint
    # ------------------------------

    single_route_start = time.time()

    # each bs must use a single route/drc combination
    # print("\n\nBS: ", topo.get_base_station_keys())
    # print("\n\nDecision Var Keys: ", decision_var_keys)
    # for route in topo.get_routes():
    #     print(f"Route {route.identifier}: {route.sequence}, {route.target}")

    
    for bs_key in topo.get_base_station_keys():
        paths_count = model.sum(model.x[key]
                                for key in decision_var_keys
                                if key.bs_key == bs_key)

        # if isinstance(paths_count, ZeroExpr):
        #     # print("ZERO EXPR: ", bs_key)
        #     continue

        model.add_constraint(paths_count == 1, 'single_route_{}'.format(bs_key))

    single_route_end = time.time()
    logging.info('    Single Route Definition: {}s'.format(single_route_end - single_route_start))

    # -------------------------------
    # Define Link Capacity Constraint
    # -------------------------------

    # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    # -> Defined in objective function
    # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

    # capacity_expressions = {}
    # # define a expression for each link
    # for link in link_list:
    #     source, destination = _min_max(link.from_node, link.to_node)
    #     capacity_expressions[(source, destination)] = model.linear_expr()

    # # sums every drc bandwidth load flowing through a link
    # for key in var_keys:
    #     link: tuple[int]
    #     for link in key.route.p1:
    #         source, destination = _min_max(link[0], link[1])
    #         capacity_expressions[(source, destination)].add_term(model.x[key], key.drc.bandwidth_bh)

    #     for link in key.route.p2:
    #         source, destination = _min_max(link[0], link[1])
    #         capacity_expressions[(source, destination)].add_term(model.x[key], key.drc.bandwidth_mh)

    #     for link in key.route.p3:
    #         source, destination = _min_max(link[0], link[1])
    #         capacity_expressions[(source, destination)].add_term(model.x[key], key.drc.bandwidth_fh)

    # # the load on every link must not exceed its capacity
    # link: Link
    # for link in link_list:
    #     source, destination = _min_max(link.from_node, link.to_node)
    #     model.add_constraint(capacity_expressions[(source, destination)] <= link.capacity, 'link capacity constraint')

    # ----------------------------
    # Define Link Delay Constraint
    # ----------------------------

    # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    # -> Granted by decision_var_keys definition
    # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

    # delay on link must not exceed the drc requirements
    # for key in decision_var_keys:
    #     if topo.get_route(key.route_id).qty_nodes() == 3:
    #         model.add_constraint(model.x[key] * topo.get_route(key.route_id).delay_backhaul <= 
    #                              drc_dict[key.drc_id].delay_bh, 'link_delay_bh')
    #     if topo.get_route(key.route_id).qty_nodes() >= 2:
    #         model.add_constraint(model.x[key] * topo.get_route(key.route_id).delay_midhaul <= 
    #                              drc_dict[key.drc_id].delay_mh, 'link_delay_mh')
    #     model.add_constraint(model.x[key] * topo.get_route(key.route_id).delay_fronthaul <= 
    #                          drc_dict[key.drc_id].delay_fh, 'link_delay_fh')

    # ------------------------------
    # Processing Capacity Constraint
    # ------------------------------

    processing_function_start = time.time()

    # for bs, gops in node_vnf_gops.items():
    #     print("BS: ", bs)
    #     print("LOAD: ", gops)
    #     print("------------------------------------------")

    # for var_key in decision_var_keys:
    #     route = topo.get_route(var_key.route_id)
    #     for hw_key in route.get_hardware_keys():
    #         hardware_processing_expressions.setdefault(hw_key, model.linear_expr())
    #         hardware_processing_expressions[hw_key] += model.sum(
    #             model.x[var_key] * node_vnf_gops[route.get_target_base_station()][function]
    #             for function in virtual_network_functions
    #             if (route.is_cu(hw_key) and function in drc_dict[var_key.drc_id].fs_cu)
    #             or (route.is_du(hw_key) and function in drc_dict[var_key.drc_id].fs_du)
    #             or (route.is_ru(hw_key) and function in drc_dict[var_key.drc_id].fs_ru)
    #         )

    hw_capacities = {}
    for key, expr in hardware_processing_expressions.items():
        hw = topo.get_hardware_by_key(key)
        hw_capacities[key] = hw.gops_capacity
        model.add_constraint(expr <= hw.gops_capacity, 'processing_capacity_{}'.format(key))

    processing_function_end = time.time()
    logging.info('    Processing Definition: {}s'.format(processing_function_end - processing_function_start))

    # ------------------------------
    #         Model Export
    # ------------------------------

    # for key, links in key_link_association.items():
    #     print(key, ": ")
    #     print("   - Backhaul:  ", links['backhaul'])
    #     print("     +  Load:  ", links['backhaul_load'])
    #     print("     + Power:  ", links['backhaul_power'])
    #     print("   - Midhaul:   ", links['midhaul'])
    #     print("     +  Load:  ", links['midhaul_load'])
    #     print("     + Power:  ", links['midhaul_power'])
    #     print("   - Fronthaul: ", links['fronthaul'])
    #     print("     +  Load:  ", links['fronthaul_load'])
    #     print("     + Power:  ", links['fronthaul_power'])
    #     print("++++++++++++++++++++++++++++++++++++++++++++++++++++++++")

    # model.add_constraint(model.x[DecisionVariableKey(55, 9, 'node14_bs1')] >= 0.5)
    model.export_as_lp('data/model_opt.lp')

    return EEPRANModel(model, centralization_constraint, ran_power_consumption,
                       net_power_consumption, mig_power_consumption, link_usage_expressions,
                       link_power_expressions,
                       hardware_processing_expressions, hw_capacities, node_vnf_gops)
