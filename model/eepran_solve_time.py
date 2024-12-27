import logging
import re
import sys
import time
from collections import defaultdict

import core.drc
import core.model
import core.topology

# ---- Logging Configuration -----
logger = logging.getLogger()
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# ----- Topology Definition -----
topos_high = [50, 100, 150, 200, 250, 300, 350, 400, 450]
topos_low = [50, 60, 70, 80, 90, 100]
topos = []
for case in [0,1,2]:
    multiplier = 1e-2
    if case == 0:
        topos = topos_high
    elif case == 1:
        multiplier = 1e-1
        topos = topos_low
    else:
        multiplier = 1.0
        topos = topos_low
    for toposize in topos:
        topo = core.topology.Topology("data/T2_{}_BS_usage.csv".format(toposize))

        topo.add_hardware(identifier=1, cpu=1, power_consumption=94.8, gops_capacity=180)
        topo.add_hardware(identifier=2, cpu=1, power_consumption=94.8, gops_capacity=180)
        topo.add_base_station(identifier=1, num_antennas=4, num_subcarriers=2048, num_used_subcarriers=1200,
                            sampling_frequency=(30.72 * 10 ** 6), ofdm_symbol_duration=(71.4 * 10 ** (-6)),
                            tau_c=192, tau_p=8, bit_quantization=12, spectral_efficiency=1.0)

        topo.load_nodes_for_eepran('data/EEPRAN_T2_{}_nodes.json'.format(toposize))
        topo.load_links_for_eepran('data/EEPRAN_T2_{}_links.json'.format(toposize), numLinksMultiplier=1, linkCapacityMultiplier=multiplier)

        topo.generate_routes_nx(origin_node="node0", k=50)
        # topo.export_routes('data/routes_T1_50.json')
        # topo.import_routes_from_json('data/routes_150.json')

        drcsDict = {drc.identifier: drc for drc in core.drc.get_drc_list_embb()}
        routesDict = {route.identifier: route for route in topo.get_routes()}

        current_deployment = core.topology.Deployment(topo.get_base_station_keys(), core.drc.get_drc_list_embb(),
                                                    topo.get_routes())

        # prefix = "T1_LC_2160p"
        # prefix = "test"
        # filename = "solutions/{}/topo_{}.csv".format(prefix, toposize)
        # with open(filename, "w+") as file:
        #     file.write('timestamp,solveTime,ranEnergy,netEnergy,migEnergy,centralization,migrations,usedMachines,drc0,drc6,drc62,drc9\n')

        eepran_model = None
        # for i in range(0, 48):
        for i in range(9, 14):
            print('--------------------------------------------------------------------------------')
            print('                         solving for Timestamp {}'.format(i))
            print('--------------------------------------------------------------------------------')
            start_time = time.time()
            eepran_model = core.model.build_eepran_model(topo, timestamp=i, centralization_cap=0,
                                                        service=core.model.SERVICE_1080P,
                                                        cr_mode=core.model.CR_MODE_CALC,
                                                        actual_deployment=current_deployment)

            eepran_model.model.parameters.timelimit = 1800
            solution = eepran_model.model.solve()

            filename = "solutions/solve_status.csv"
            with open(filename, "a+") as file:
                # file.write('case,toposize,timestamp,status\n')
                file.write("{},{},{},{}\n".format(
                    case,
                    toposize,
                    i,
                    eepran_model.model.solve_details.status))

            if solution is None:
                print('==========================')
                print('!!! SOLUTION NOT FOUND !!!')
                print('==========================')
                continue

            # ---------------------------------------------------------------
            # -------------------- Solution Presentation --------------------
            # ---------------------------------------------------------------

            turned_on_machines = []
            num_turned_on_machines = 0
            total_energy_consumed = 0.0
            num_machines_per_time = []
            drcs_per_time = defaultdict(int)

            print('----------------------------------------')
            total_energy_consumed += eepran_model.model.solution.get_objective_value()
            print('Objective Value: {} [w]'.format(eepran_model.model.solution.get_objective_value()))
            print('Centralization: {}'.format(
                eepran_model.model.solution.get_value(eepran_model.centralizationContraint.left_expr)))
            print('Ran Power Consumption: {}'.format(eepran_model.model.solution.get_value(eepran_model.ranPowerExpr)))
            print('Net Power Consumption: {}'.format(eepran_model.model.solution.get_value(eepran_model.netPowerExpr)))
            print('Mig Power Consumption: {}'.format(eepran_model.model.solution.get_value(eepran_model.migPowerExpr)))

            print('----------------------------------------')
            print('                Solution                ')
            solution_keys = []
            drcs_per_bs = {}
            for key in eepran_model.model.x:
                if eepran_model.model.x[key].solution_value > 10 ** (-3):
                    # print("route={}, drc={}, bs={} -> {}".format(topo.get_route(key.route_id).sequence, key.drc_id, key.bs_key, eepran_model.model.x[key].solution_value))
                    print("route={}, drc={}, bs={} -> {}".format(key.route_id, key.drc_id, key.bs_key,
                                                                eepran_model.model.x[key].solution_value))
                    print("  |-route={} -> {}".format(key.route_id, topo.get_route(key.route_id).sequence))
                    drcs_per_time[key.drc_id] += 1
                    bs_id = re.findall(r'\d+', key.bs_key)
                    drcs_per_bs[bs_id[0]] = key.drc_id
                    solution_keys.append(key)

            # bs_filename = "solutions/{}/topo_{}_time_{}_drc_per_bs.csv".format(prefix, toposize, i)
            # with open(bs_filename, "w+") as file:
            #     file.write("bs,drc\n")
            #     for key, value in drcs_per_bs.items():
            #         file.write("{},{}\n".format(key, value))

            for key in eepran_model.model.y:
                if eepran_model.model.y[key].solution_value > 10 ** (-3):
                    print("HW: {} -> Turned On Units: {}".format(key, eepran_model.model.y[key].solution_value))
                    num_turned_on_machines += eepran_model.model.y[key].solution_value

            # print('----------------------------------------')
            # print('        Centralization Locations        ')

            # for key in eepran_model.model.z:
            #     if eepran_model.model.z[key].solution_value != 0:
            #         print('node={}, function={} -> {}'.format(key.node_key, key.function_key, eepran_model.model.z[key].solution_value))

            # print('----------------------------------------')
            # print('              VNF Positions             ')

            # drc_dict = {}
            # for drc in core.drc.get_drc_list():
            #     drc_dict[drc.identifier] = drc

            # for key in eepran_model.model.x:
            #     if eepran_model.model.x[key].solution_value > 10**(-3):
            #         route = topo.get_route(key.route_id)
            #         print('{}:'.format(key.bs_key))
            #         print('    CU({} -> {})'.format(route.sequence[0], drc_dict[key.drc_id].fs_cu))
            #         print('    DU({} -> {})'.format(route.sequence[1], drc_dict[key.drc_id].fs_du))

            print('----------------------------------------')
            print('                 HW Usage               ')

            switch_on = []
            switch_off = []
            hw_usage = defaultdict(float)
            hw_capacity = defaultdict(int)
            for key, expr in eepran_model.hwUsageExprs.items():
                usg = eepran_model.model.solution.get_value(expr)
                if usg > 0.01:
                    print('{} USAGE IS {:.2f} GOPS ({:.2f}%)'.format(key, usg, usg / eepran_model.hwCapacities[key] * 100))
                    hw_id = re.findall(r'\d+', key)
                    hw_usage[hw_id[0]] += usg
                    hw_capacity[hw_id[0]] += eepran_model.hwCapacities[key]
                    if key not in turned_on_machines:
                        switch_on.append(key)
                else:
                    if key in turned_on_machines:
                        switch_off.append(key)

            # hw_filename = "solutions/{}/topo_{}_time_{}_hw.csv".format(prefix, toposize, i)
            # with open(hw_filename, "w+") as file:
            #     file.write("hw,usage,capacity\n")
            #     for key in hw_usage:
            #         file.write("{},{},{}\n".format(key, hw_usage[key], hw_capacity[key]))

            # print('                 CHANGES                ')

            # for key in switch_on:
            #     print(' (+) {}'.format(key))
            #     turned_on_machines.append(key)
            # for key in switch_off:
            #     print(' (-) {}'.format(key))
            #     turned_on_machines.remove(key)

            # num_machines_per_time.append([len(turned_on_machines), i])

            print('----------------------------------------')
            print('                Link Usage              ')

            # net_filename = "solutions/{}/topo_{}_time_{}_network.csv".format(prefix, toposize, i)
            # with open(net_filename, "w+") as file:
            #     file.write("node1,node2,usage\n")
            #     for key, expr in eepran_model.linkUsageExprs.items():
            #         datarate = eepran_model.model.solution.get_value(expr)
            #         if datarate < 10e-12:
            #             datarate = 0.0

            #         n1 = re.findall(r'[^\d|\w]*(\d+)', key.split(',')[0])
            #         n2 = re.findall(r'[^\d|\w]*(\d+)', key.split(',')[1])
            #         file.write("{},{},{}\n".format(n1[0], n2[0], datarate))

            #         if datarate == 0.0:
            #             continue

            #         power = eepran_model.model.solution.get_value(eepran_model.linkPowerExprs[key])
            #         print('{}: \n DATARATE IS {:.2f}gbps k\n POWER USAGE IS {:.2f}W'.format(key, datarate, power))


            print('----------------------------------------')
            print('               Migrations               ')

            mig_count = 0
            for key in eepran_model.model.x:
                if eepran_model.model.x[key].solution_value > 10 ** (-3):
                    for vnf in drcsDict[key.drc_id].fs_cu:
                        cu = routesDict[key.route_id].sequence[0]
                        if current_deployment.IsDeployedIn(key.bs_key, vnf, cu) == 0:
                            mig_count += 1
                            # print("{} of {} changed to {}".format(vnf, key.bs_key, cu))
                    for vnf in drcsDict[key.drc_id].fs_du:
                        du = routesDict[key.route_id].sequence[1]
                        if current_deployment.IsDeployedIn(key.bs_key, vnf, du) == 0:
                            mig_count += 1
                            # print("{} of {} changed to {}".format(vnf, key.bs_key, du))

            if mig_count > 0:
                print('{} migrations ocurred'.format(mig_count))
            else:
                print('NO migrations executed')
            print('----------------------------------------')

            # filename = "solutions/{}/topo_{}.csv".format(prefix, toposize)
            filename = "solutions/time_eval.csv"
            with open(filename, "a+") as file:
                # file.write('toposize,timestamp,solveTime,mipGap,ranEnergy,netEnergy,migEnergy,centralization,migrations,usedMachines,drc0,drc6,drc62,drc9\n')
                file.write("{},{},{},{},{},{},{},{},{},{},{},{},{},{}\n".format(
                    toposize,
                    i,
                    eepran_model.model.solve_details.time,
                    eepran_model.model.solve_details.mip_relative_gap,
                    eepran_model.model.solution.get_value(eepran_model.ranPowerExpr),
                    eepran_model.model.solution.get_value(eepran_model.netPowerExpr),
                    eepran_model.model.solution.get_value(eepran_model.migPowerExpr),
                    eepran_model.model.solution.get_value(eepran_model.centralizationContraint.left_expr),
                    mig_count,
                    num_turned_on_machines,
                    drcs_per_time[0], drcs_per_time[6], drcs_per_time[62], drcs_per_time[9],))


            # ---------------------------------------------------------------
            # -------------------- Deployment Definition --------------------
            # ---------------------------------------------------------------

            current_deployment = core.topology.Deployment(topo.get_base_station_keys(), core.drc.get_drc_list_embb(),
                                                        topo.get_routes())
            for key in eepran_model.model.x:
                if eepran_model.model.x[key].solution_value > 10 ** (-3):
                    current_deployment.SetDeploy(key.bs_key, key.drc_id, key.route_id)

            print('--------------------------------------------------------------------------------')

            end_time = time.time()
            if eepran_model is not None:
                print("Total Solving Time: {}".format(end_time - start_time))
                print("Solution Status: ", eepran_model.model.solve_details.status)
                print("total Energy: ", total_energy_consumed)
                print("num_HW: ", num_machines_per_time)
                print("DRC: ", drcs_per_time)
            else:
                print("Model not defined!")
