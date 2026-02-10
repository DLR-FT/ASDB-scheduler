# TDMA scheduler
"""TDMA Scheduler
Generate a schedule for a given HSDN network and VLs
"""

# Import packages
import collections
import itertools
import json
import sys
import logging
import os

import argparse
import jsonschema
import networkx as nx

from ortools.sat.python import cp_model

from visualizer import (
    plot_graph,
    plot_path,
    export_plantuml,
    export_dot,
    print_schedule_in_graph,
    plotly_gantt,
)


# matplotlib.use("pgf")
# matplotlib.rcParams.update({
#     "pgf.texsystem": "pdflatex",
#     #'font.family': 'serif',
#     'text.usetex': True,
#     #'pgf.rcfonts': False,
# })


def main():
    """Scheduler main function"""

    # Define command line arguments
    parser = argparse.ArgumentParser(
        prog="scheduler",
        description="Scheduler for TDMA",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "input-scheduler",
        help="scheduler input file name",
        nargs="?",
        default="example_network.json",
    )
    parser.add_argument(
        "-o",
        "--output-folder",
        help="output folder name",
        default="output",
        required=False,
    )
    parser.add_argument(
        "-i",
        "--input-schema",
        help="input file schema",
        default="schema_input_scheduler.json",
        required=False,
    )
    parser.add_argument(
        "-s",
        "--schedule-schema",
        help="output schedule file schema",
        default="schema_output_scheduler.json",
        required=False,
    )
    parser.add_argument(
        "-c",
        "--config-schema",
        help="output config file schema",
        default="schema_output_config.json",
        required=False,
    )
    parser.add_argument(
        "-m",
        "--maximum-cycle-time",
        help="TDMA schedule maximum cycle time",
        default=None,
        required=False,
    )
    parser.add_argument(
        "-t",
        "--maximum-solve-time",
        help="TDMA scheduler maximum solve time in seconds",
        default=None,
        required=False,
    )
    parser.add_argument(
        "-l",
        "--log-level",
        help="log level",
        choices=["debug", "info", "warning", "warn", "error", "fatal", "critical"],
        default="info",
        required=False,
    )
    # parser.print_help()

    # Read command line inputs
    args = vars(parser.parse_args())
    # print("args:", args)
    input_file_name = args["input-scheduler"]
    output_folder_name = args["output_folder"]
    input_schema_name = args["input_schema"]
    schedule_schema_name = args["schedule_schema"]
    config_schema_name = args["config_schema"]
    schedule_maximum = args["maximum_cycle_time"]
    solve_time_maximum = args["maximum_solve_time"]
    log_level = args["log_level"]

    script_dir = os.path.dirname(__file__)
    output_folder_path = os.path.join(script_dir, output_folder_name)

    # Create output folder if not exists
    os.makedirs(output_folder_path, exist_ok=True)

    # Configure logging
    logging.basicConfig(
        format="%(asctime)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.getLevelNamesMapping()[log_level.upper()],
    )

    # General graph parameter
    general_hop_latency = -1
    minimum_guard_width = 5

    # Load scheduler input json schema
    with open(
        os.path.join(script_dir, input_schema_name), encoding="utf-8"
    ) as schema_input_scheduler_file:
        # sched_int_in_3
        schema_input_scheduler = json.load(schema_input_scheduler_file)

    # Load scheduler output config schema
    with open(
        os.path.join(script_dir, config_schema_name), encoding="utf-8"
    ) as schema_output_config_file:
        # sched_int_in_3
        schema_output_config = json.load(schema_output_config_file)

    # Load input json file
    with open(input_file_name, encoding="utf-8") as input_example_file:
        input_json = json.load(input_example_file)

    # sched_int_in_2
    jsonschema.validate(instance=input_json, schema=schema_input_scheduler)

    minimum_guard_width = input_json["min_gbt"]

    # Read time sync priorities
    time_sync_priorities = input_json["time_sync_priorities"]
    # Create dictionary mapping nap ids to their time sync priority
    time_sync_priorities_dict = {
        t["nap_id"]: t["priority"] for t in time_sync_priorities
    }

    with open(
        os.path.join(script_dir, schedule_schema_name), encoding="utf-8"
    ) as schema_output_scheduler_file:
        schema_output_scheduler = json.load(schema_output_scheduler_file)

    def _read_graph_example():
        """Generate input graph example

        Read input file and create networkx graph from the input

        :return G: networkx graph
        :return general_hop_latency: Network hop latency
        """
        # Generate test graph
        test_graph = nx.MultiGraph(nx.circulant_graph(10, [1]))
        test_graph.add_edge(1, 2)
        test_graph.add_edge(2, 3)
        # G = nx.MultiGraph(nx.complete_graph(5))
        # Add latency to edges
        nx.set_edge_attributes(test_graph, 1, "latency")
        # print(nx.get_edge_attributes(G, "latency").values())
        hop_latency = max(nx.get_edge_attributes(test_graph, "latency").values())
        logging.info(f"General hop latency: {hop_latency}")
        logging.info("Test graph generated")
        return test_graph, hop_latency

    def source_target_to_label(source_targets):
        """Get label to VL source or target

        :param source_target: VL source or target dict or list of source or target dict

        :return label: NAP id or NAP id with interface id tuple if outer domain
        """

        def single_label(nap_interface_dict):
            # Check if only NAP is the source/target
            if "interface_id" not in nap_interface_dict or (
                "interface_id" in nap_interface_dict
                and nap_interface_dict["interface_id"] == ""
            ):
                return nap_interface_dict["nap_id"]
            return (
                nap_interface_dict["nap_id"],
                nap_interface_dict["interface_id"],
            )

        if isinstance(source_targets, list):
            return [single_label(target) for target in source_targets]
        if isinstance(source_targets, dict):
            return single_label(source_targets)
        logging.error(f"Unknown source target: {source_targets}")
        return None

    def read_graph(network_dict):
        """Read graph from file and output networkx graph

        :param network_dict: Input network dictionary
        :return G: networkx graph
        :return general_hop_latency: Network hop latency
        :return nap_ids: List of NAP ids
        """
        output_graph = nx.MultiGraph()
        inner_domain_links = network_dict["inner_domain_links"]
        nap_id_list = []

        for nap_interface in inner_domain_links:
            for interface in nap_interface["interface_list"]:
                # Create edge from NAP to interface
                output_graph.add_edge(
                    interface["nap_id"],
                    interface["interface_id"],
                    latency=0,
                    weight=1.5,
                    function="nap_inner_interface",
                )
                nap_id_list.append(interface["nap_id"])
                # Add functionality to created nodes
                output_graph.nodes[interface["nap_id"]]["function"] = "nap"
                output_graph.nodes[interface["interface_id"]][
                    "function"
                ] = "inner_domain_interface"
            # Create edge between inner domain interfaces
            output_graph.add_edge(
                nap_interface["interface_list"][0]["interface_id"],
                nap_interface["interface_list"][1]["interface_id"],
                latency=nap_interface["latency"],
                weight=3,
                function="inner_link",
            )
            # Add nap names to NAPs if available
            if "nap_name" in nap_interface:
                output_graph.nodes[nap_interface["nap"]]["name"] = (
                    nap_interface["nap_name"] + f"\n{nap_interface['nap']}"
                )
            else:
                pass
                # print("nap name not in input found!!!!!")
            if "connected_nap_name" in nap_interface:
                output_graph.nodes[nap_interface["connected_nap"]]["name"] = (
                    nap_interface["connected_nap_name"]
                )
            else:
                pass
                # print("connected nap name not found in output!!")
        # Read outer domain interfaces
        outer_domain_links = network_dict["outer_domain_interfaces"]
        outer_domain_ids = []
        for outer_domain in outer_domain_links:
            output_graph.add_edge(
                (outer_domain["nap_id"], outer_domain["interface_id"]),
                outer_domain["nap_id"],
                latency=0,
                weight=3,
                function="nap_outer_interface",
            )
            output_graph.add_edge(
                outer_domain["nap_id"],
                (outer_domain["nap_id"], outer_domain["interface_id"]),
                latency=0,
                weight=3,
                function="nap_outer_interface",
            )
            outer_domain_ids.append(
                (outer_domain["nap_id"], outer_domain["interface_id"])
            )
            # Add indicator to outer domain node
            output_graph.nodes[(outer_domain["nap_id"], outer_domain["interface_id"])][
                "function"
            ] = "outer_domain_interface"

        hop_latency_calculated = max(
            nx.get_edge_attributes(output_graph, "latency").values()
        )
        logging.info(
            "General calculated hop latency: %s, from json: %s",
            hop_latency_calculated,
            network_dict["common_latency_value"],
        )
        logging.info("Graph successfully read from json network representation")
        return (
            output_graph,
            network_dict["common_latency_value"],
            list(set(nap_id_list)),
            outer_domain_ids,
        )

    network_graph, general_hop_latency, nap_ids, outer_domain_ids = read_graph(
        input_json
    )
    plot_graph(
        network_graph, "new_network.png", output_directory_name=output_folder_path
    )

    # Export graph as a DOT file
    export_dot(
        network_graph, "network_export.dot", output_directory_name=output_folder_path
    )

    # G = nx.MultiGraph(nx.bfs_tree(G, 0))
    # nx.set_edge_attributes(network_graph, 1, "latency")

    # Generate node IDs
    node_ids = network_graph.nodes

    def _read_vls_example():
        """Generate test virtual links (VL)

        :return all_vls_array: 2D array of the input VLS
        :return all_vls: Dictionary of the VLs, indexed by VL IDs
        """
        # id, source, target, max_latency, bandwidth, allow_retransmission
        all_vls_2d_array = [
            ["1", 0, 1, 20, 14, False],
            ["2", 1, 0, 21, 15, False],
            ["3", 1, 5, 22, 16, False],
            ["4", 1, 7, 23, 17, False],
            ["5", 0, [1, 5, 9], 50, 5, False],
        ]
        # all_vls_array = [["5", 0, [1, 9], 50, 7, False]]
        all_vls_dict = {}
        for virtual_link in all_vls_2d_array:
            all_vls_dict[virtual_link[0]] = {
                "source": virtual_link[1],
                "target": virtual_link[2],
                "max_latency": virtual_link[3],
                "bandwidth": virtual_link[4],
                "allow_retransmission": virtual_link[5],
            }
        logging.info("VLs generated")
        logging.info("All VLs: %s", all_vls_dict)
        return all_vls_2d_array, all_vls_dict

    def read_vls(network_dict):
        """Read VLs from network dictionary

        :param network_dict: Input network dictionary
        :return all_vls_array: 2D array of the input VLS
        :return all_vls: Dictionary of the VLs, indexed by VL IDs
        """
        all_vls_2d_array = []
        all_vls_dict = {}
        vls_json = network_dict["virtual_links"]
        for vl_current in vls_json:
            # If VL is not active don't schedule it
            if not vl_current["vl_active"]:
                continue
            for vl_number, vl_id in enumerate(vl_current["id"]):
                vl_current_data_size = (
                    2 * vl_current["data_size"]
                    if vl_current["allow_retransmissions"]
                    else vl_current["data_size"]
                )
                all_vls_2d_array.append(
                    [
                        vl_id,
                        vl_current["source_nap"],
                        vl_current["target_naps"],
                        vl_current["max_allowed_latency"],
                        vl_current_data_size,
                        vl_current["allow_retransmissions"],
                    ]
                )
                all_vls_dict[vl_id] = {
                    "source": source_target_to_label(vl_current["source_nap"]),
                    "target": source_target_to_label(vl_current["target_naps"]),
                    "max_latency": vl_current["max_allowed_latency"],
                    "bandwidth": vl_current_data_size,
                    "allow_retransmission": vl_current["allow_retransmissions"],
                    "redundant_to": [a for a in vl_current["id"] if a != vl_id],
                    "interface_channel": vl_current["interface_channel"],
                    "vl_active": vl_current["vl_active"],
                    "local_destination": vl_current["local_destination"],
                }
                if "deduplication_method" in vl_current:
                    all_vls_dict[vl_id]["deduplication_method"] = vl_current[
                        "deduplication_method"
                    ]
                if "deduplication_source" in vl_current:
                    all_vls_dict[vl_id]["deduplication_source"] = vl_current[
                        "deduplication_source"
                    ]
                if "inner_domain_interface" in vl_current:
                    all_vls_dict[vl_id]["inner_domain_interface"] = vl_current[
                        "inner_domain_interface"
                    ][vl_number]

        return all_vls_2d_array, all_vls_dict

    all_vls_array, all_vls = read_vls(input_json)
    # Extract keys to ID VL IDs
    vl_ids = all_vls.keys()

    # Test if graph is connected
    if nx.is_connected(network_graph):
        logging.info("Input graph is connected")
    else:
        logging.warning("Input graph is not connected!")

    # Test path
    # for path in nx.all_simple_edge_paths(G, source=0, target=3):
    #    print(path)

    def replace_node_name(old_node_names, new_node_name, path):
        """
        Helper function to replace node names in graph paths
        """
        new_path = []
        for edge in path:
            e0 = edge[0] if edge[0] not in old_node_names else new_node_name
            e1 = edge[1] if edge[1] not in old_node_names else new_node_name
            new_path.append((e0, e1, edge[2]))
        return new_path

    # Folder for paths visual representation
    output_folder_paths_name = os.path.join(output_folder_path, "paths")
    # Create table with all possible paths
    vls_possible_paths = {}
    number_of_paths: int = 0
    for vl_id in vl_ids:
        vl = all_vls[vl_id]
        target_paths = []
        for target in vl["target"]:
            possible_paths = nx.all_simple_edge_paths(
                network_graph, source=vl["source"], target=target
            )
            if vl["local_destination"]:
                attached_nap = target[0]
                # Copy network
                network_graph_copy = network_graph.copy()
                # Get all edges from the attached NAP
                all_edges = list(set(list(network_graph_copy.edges(attached_nap))))
                # Create two NAPs replacing the attached NAP and connect all previously connected nodes to it
                network_graph_copy.add_edges_from(
                    [(attached_nap + "_1", e[1]) for e in all_edges]
                )
                network_graph_copy.add_edges_from(
                    [(attached_nap + "_2", e[1]) for e in all_edges]
                )
                network_graph_copy.remove_node(attached_nap)
                # Get all simple edge paths for the new network
                all_shortest_paths = list(
                    nx.all_simple_edge_paths(
                        network_graph_copy, source=vl["source"], target=target
                    )
                )
                possible_paths = [
                    replace_node_name(
                        [attached_nap + "_1", attached_nap + "_2"], attached_nap, p
                    )
                    for p in all_shortest_paths
                ]
                # Remove paths using only the attached NAP or their interfaces
                possible_paths = [p for p in possible_paths if len(p) > 4]
            suitable_paths = []
            for path in possible_paths:
                max_latency = all_vls[vl_id]["max_latency"]
                path_latency = sum(network_graph.edges[e]["latency"] for e in path)
                # print(f"Max: {max_latency}, Latency: {path_latency}")
                if path_latency < max_latency:
                    suitable_paths.append(path)
            target_paths.append(suitable_paths)
        vls_possible_paths[vl_id] = []
        for p in itertools.product(*target_paths):
            vls_possible_paths[vl_id].append(
                list(set(list(itertools.chain.from_iterable(p))))
            )
        # Check if source is in the outer domain
        if vl["source"] in outer_domain_ids:
            if vl["local_destination"]:
                continue
            # Get NAP connected to the outer domain interface
            connected_nap = next(network_graph.neighbors(vl["source"]))
            vls_possible_paths_removed_branching = []
            for path in vls_possible_paths[vl_id]:
                # Count number of branches on source NAP
                source_branches = [p for p in path if p[0] == connected_nap]
                if len(source_branches) <= 1:
                    # Only add paths with one or fewer branches
                    vls_possible_paths_removed_branching.append(path)
                else:
                    logging.debug(f"Removed path {path} as it branches as source NAP")
            vls_possible_paths[vl_id] = vls_possible_paths_removed_branching
        number_of_paths += len(vls_possible_paths[vl_id])
    logging.info(f"Possible VL paths created. Number of paths: {number_of_paths}")
    logging.info(f"Possible paths: {vls_possible_paths}")

    for n, path in enumerate(vls_possible_paths[list(vl_ids)[0]]):
        plot_path(
            path,
            network_graph,
            output_filename=f"A_start_path_{n}",
            output_directory_name=output_folder_paths_name,
        )
    # sys.exit(0)
    # Remove NAP nodes from paths leaving only interface nodes
    possible_paths_removed_naps = collections.defaultdict(list)
    for vl_id in vl_ids:
        for path in vls_possible_paths[vl_id]:
            # Find connected interfaces for each NAP in path
            new_path = []
            for nap_id in nap_ids:
                incoming_interface = []
                interfaces_to_connect = []
                for e in path:
                    # Outgoing edge
                    if nap_id == e[0]:
                        interfaces_to_connect.append(e[1])
                    # Input edge
                    elif nap_id == e[1]:
                        pass
                        # incoming_interface.append(e[0])
                interfaces_to_connect = list(set(interfaces_to_connect))
                # if len(incoming_interface) > 1:
                # print("Error with:", incoming_interface)
                # print("Path:", path)
                for new_e in itertools.product(
                    incoming_interface, interfaces_to_connect
                ):
                    new_path.append((new_e[0], new_e[1], 0))
            # Add edges between interfaces
            for e in path:
                if e[0] not in nap_ids and e[1] not in nap_ids:
                    new_path.append(e)
            possible_paths_removed_naps[vl_id].append(new_path)
    print("Possible paths, removed naps:", possible_paths_removed_naps)
    vls_possible_paths = possible_paths_removed_naps

    for n, path in enumerate(vls_possible_paths[list(vl_ids)[0]]):
        plot_path(
            path,
            network_graph,
            output_filename=f"B_remove_naps_path_{n}",
            output_directory_name=output_folder_paths_name,
        )

    # Remove outer domain interfaces from path
    possible_paths_removed_outer_domain_interfaces = collections.defaultdict(list)
    for vl_id in vl_ids:
        for path in vls_possible_paths[vl_id]:
            new_path = [
                a
                for a in path
                if a[0] not in outer_domain_ids and a[1] not in outer_domain_ids
            ]
            possible_paths_removed_outer_domain_interfaces[vl_id].append(new_path)
    vls_possible_paths = possible_paths_removed_outer_domain_interfaces

    # Remove paths that do not use the inner domain interface associated with the VLs
    possible_paths_removed_false_inner_domain_interfaces = collections.defaultdict(list)
    for vl_id in vl_ids:
        # Check if VL has a needed inner domain interface
        if "inner_domain_interface" in all_vls[vl_id]:
            needed_interface = all_vls[vl_id]["inner_domain_interface"]
            for path in vls_possible_paths[vl_id]:
                # Only accept paths that contain the needed inner domain interface as a sending interface
                if [a for a in path if a[0] == needed_interface]:
                    possible_paths_removed_false_inner_domain_interfaces[vl_id].append(
                        path
                    )
        else:
            possible_paths_removed_false_inner_domain_interfaces[vl_id] = (
                vls_possible_paths[vl_id]
            )
    vls_possible_paths = possible_paths_removed_false_inner_domain_interfaces

    # Print paths of first VL
    for n, path in enumerate(vls_possible_paths[list(vl_ids)[0]]):
        plot_path(
            path,
            network_graph,
            output_filename=f"C_remove_odi_path_{n}",
            output_directory_name=output_folder_paths_name,
        )

    # Create VL assignment model for OR tools
    # Creates the model and declare CP-SAT solver.
    assignment_model = cp_model.CpModel()
    assignment_model.name = "vl_assignment"

    # Creates the variables based on possible VL paths
    vl_paths_variables = {}
    vl_variables_to_path = {}
    for vl_id in vl_ids:
        vl_paths_variables[vl_id] = []
        for path in vls_possible_paths[vl_id]:
            vl_paths_variables[vl_id].append(
                assignment_model.NewBoolVar(str(vl_id) + "_" + str(path))
            )
            vl_variables_to_path[vl_paths_variables[vl_id][-1]] = path
    # Add helper variable for objective function
    assignment_horizon = (
        max(a[4] for a in all_vls_array) * len(vl_ids) * len(network_graph.edges)
    )
    objective_variable = assignment_model.NewIntVar(
        0,
        assignment_horizon,
        "objective",
    )
    # print(model)

    # Creates the constraints.
    # Each of the VLs gets exactly one path
    for vl_id in vl_ids:
        assignment_model.Add(sum(vl_paths_variables[vl_id]) == 1)

    # Create redundancy constraints
    # Find groups of redundant VLs
    vl_ids_copy = list(vl_ids).copy()
    redundant_vls = []
    while len(vl_ids_copy) > 0:
        current_id = vl_ids_copy.pop()
        if len(all_vls[current_id]["redundant_to"]) == 0:
            continue
        redundant_vls.append(all_vls[current_id]["redundant_to"] + [current_id])
        vl_ids_copy = [a for a in vl_ids_copy if a not in redundant_vls[-1]]
    logging.info("Redundant VLs: %s", redundant_vls)

    # Create list of reversed edges
    network_graph_reversed_edges = [(e[1], e[0], e[2]) for e in network_graph.edges]

    # Assign boolean variable to each edge for each redundant VL in the VL groups
    for vl_group in redundant_vls:
        # Dictionary with list as values assigning variables to graph edges
        edge_to_variables_dict = collections.defaultdict(list)
        for e in list(network_graph.edges) + network_graph_reversed_edges:
            for vl_id in vl_group:
                variable_name = str(vl_id) + "_" + str(e)
                # print("Variable name:", variable_name)
                # Create variable for using the edge
                edge_to_variables_dict[e].append(
                    assignment_model.NewIntVar(0, 1, variable_name)
                )
                for path_variable in vl_paths_variables[vl_id]:
                    # print("Path variable real name:", path_variable.Name(), " | Edge:", str(e))
                    if str(e) in path_variable.Name():
                        # print(f"Add {e} to path variable {path_variable.Name()}")
                        assignment_model.Add(
                            edge_to_variables_dict[e][-1] >= path_variable
                        )
            assignment_model.AddAtMostOne(edge_to_variables_dict[e])
            # print("Edge to variables dict for edge", edge_to_variables_dict[e])

    # Create helper variable for maximum bandwidth over edges
    edge_expressions = []
    for e in network_graph.edges:
        relevant_variables = []
        for vl_id in vl_ids:
            for path in vl_paths_variables[vl_id]:
                if str(e) in str(path):
                    relevant_variables.append(
                        cp_model.LinearExpr.Term(path, all_vls[vl_id]["bandwidth"])
                    )
        edge_expressions.append(cp_model.LinearExpr.Sum(relevant_variables))
    assignment_model.AddMaxEquality(objective_variable, edge_expressions)

    # Add objective
    # Minimize the maximum bandwidth over all edges
    assignment_model.Minimize(objective_variable)

    # print(assignment_model.ModelStats())
    # Creates a solver and solves the model.
    logging.info("Start path assignment solver")
    assignment_solver = cp_model.CpSolver()
    if log_level == "debug":
        assignment_solver.parameters.log_search_progress = True
        assignment_solver.parameters.log_to_stdout = True
    status = assignment_solver.Solve(assignment_model)
    logging.info("Path assignment solver finished")

    # Statistics.
    logging.info("\nStatistics assignment solver")
    logging.info(f"  - conflicts: {assignment_solver.NumConflicts()}")
    logging.info(f"  - branches : {assignment_solver.NumBranches()}")
    logging.info(f"  - wall time: {assignment_solver.WallTime()}s")
    logging.info(f"Model statistics:{assignment_model.ModelStats()}\n")

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        if status == cp_model.OPTIMAL:
            logging.info("Solver status: Optimal")
        if status == cp_model.FEASIBLE:
            logging.info("Solver status: Feasible")
        logging.info(f"Solver objective value: {assignment_solver.ObjectiveValue()}")
        logging.info("Chosen paths for corresponding VLs:")
        used_paths = {}
        for vl_id in vl_ids:
            for path in vl_paths_variables[vl_id]:
                if assignment_solver.Value(path) == 1:
                    logging.info(f"{path}\t{assignment_solver.Value(path)}")
                    used_paths[vl_id] = vl_variables_to_path[path]
        print("Used paths:", used_paths)
    else:
        logging.warning(
            "Could not find feasible solution to assignment task! Program will exit!"
        )
        sys.exit()

    # Create model for TDMA scheduling problem
    tdma_model = cp_model.CpModel()
    tdma_model.SetName("tdma_model")

    # Create variables
    # Jobs
    jobs_data = []
    # Assign each VL a number of job variables
    vl_id_to_jobs = {}
    for vl_id in vl_ids:
        used_path = used_paths[vl_id]
        # ALT: used_nodes = list(set([a[0] for a in used_path] + [a[1] for a in used_path]))
        used_nodes = list({a[0] for a in used_path})
        vl_id_to_jobs[vl_id] = [(a, all_vls[vl_id]["bandwidth"]) for a in used_nodes]
        jobs_data.append([(a, all_vls[vl_id]["bandwidth"]) for a in used_nodes])
    # Defines horizon for model variables
    # Sum of all VL data_size + GBT + GHL times the number of nodes in the network
    horizon = (
        sum(
            task[1] + minimum_guard_width + general_hop_latency
            for job in jobs_data
            for task in job
        )
        * network_graph.number_of_nodes()
    )
    if schedule_maximum is not None:
        horizon = int(schedule_maximum)
    logging.info(f"Defined jobs (machine, duration): {jobs_data}")
    logging.info(f"Job horizon: {horizon}")

    # Named tuple to store information about created variables.
    task_type = collections.namedtuple("task_type", "start end interval")
    # Named tuple to manipulate solution information.
    assigned_task_type = collections.namedtuple(
        "assigned_task_type", "start end job index duration"
    )

    # Creates job intervals and add to the corresponding machine lists.
    all_tasks = {}
    machine_to_intervals = collections.defaultdict(list)

    for vl_id, job in zip(vl_ids, jobs_data):
        print(f"job_id: {vl_id}, job: {job}")
        for task_id, task in enumerate(job):
            print(f"task_id: {task_id}, task: {task}")
            machine, duration = task
            suffix = f"_{vl_id}_{task_id}"
            start_var = tdma_model.NewIntVar(0, horizon, "start" + suffix)
            end_var = tdma_model.NewIntVar(0, horizon, "end" + suffix)
            interval_var = tdma_model.NewIntervalVar(
                start_var, duration + minimum_guard_width, end_var, "interval" + suffix
            )
            all_tasks[vl_id, task_id] = task_type(
                start=start_var, end=end_var, interval=interval_var
            )
            machine_to_intervals[machine].append(interval_var)

    # Create and add disjunctive constraints.
    for machine in node_ids:
        tdma_model.AddNoOverlap(machine_to_intervals[machine])

    # Precedences inside a job.
    for vl_id in list(vl_ids):
        used_path = used_paths[vl_id]
        # List of used variable indices
        used_variable_indices = []
        for e in used_path:
            # Check if path is only one hop, if so skip as it doesn't have precedence to other jobs
            if len(used_path) == 1:
                continue
            # Get variable for the current edge e
            source, target, _ = e
            source_index: None = None
            for index, a in enumerate(vl_id_to_jobs[vl_id]):
                if a[0] == source:
                    source_index = index
            source_var = all_tasks[vl_id, source_index]
            # Get all used outgoing edges of the current target NAP
            target_nap = list(nx.all_neighbors(network_graph, target))
            target_nap.remove(source)
            target_nap = target_nap[0]
            target_interfaces = [
                a
                for a in nx.all_neighbors(network_graph, target_nap)
                if a not in outer_domain_ids and a != target
            ]
            targets = [a for a in used_path if a[0] in target_interfaces]
            # Add constraint for each target edge
            for target_edge in targets:
                # Get variable for the target edge
                target_index = None
                for index, a in enumerate(vl_id_to_jobs[vl_id]):
                    if a[0] == target_edge[0]:
                        target_index = index
                target_var = all_tasks[vl_id, target_index]
                used_variable_indices.append(source_index)
                # Skip last precedence constraint for locally scheduled VLs
                if (
                    all_vls[vl_id]["local_destination"]
                    and target_edge[0] in all_vls[vl_id]["inner_domain_interface"]
                ):
                    print("Skipped the following:")
                    print(
                        f"Path {e}, source index: {source_index}, target index: {target_index}, "
                        + f"source_var: {source_var.start.Name()}, target_var: {target_var.start.Name()}\n------\n"
                    )
                    used_variable_indices.append(source_index)
                    continue
                print(
                    f"Path {e}, source index: {source_index}, target index: {target_index}, "
                    + f"source_var: {source_var.start.Name()}, target_var: {target_var.start.Name()}"
                )
                # Add constraint
                tdma_model.Add(
                    target_var.start == source_var.start + general_hop_latency
                )

    # Makespan objective.
    obj_var = tdma_model.NewIntVar(0, horizon, "makespan")
    obj_value = [a[1].end for a in all_tasks.items()]
    print("obj_value:", obj_value)
    tdma_model.AddMaxEquality(obj_var, obj_value)
    tdma_model.Minimize(obj_var)
    # Creates the solver and solve
    tdma_solver = cp_model.CpSolver()
    if log_level == "debug":
        tdma_solver.parameters.log_search_progress = True
        tdma_solver.parameters.log_to_stdout = True
    # Add maximum solve time if set with CLI argument
    if solve_time_maximum is not None:
        tdma_solver.parameters.max_time_in_seconds = int(solve_time_maximum)
    status = tdma_solver.Solve(tdma_model)
    status_name = tdma_solver.StatusName(status)

    # Statistics.
    print("\nStatistics TDMA solver")
    print(f"  - status code: {status}, name: {status_name}")
    print(f"  - conflicts: {tdma_solver.NumConflicts()}")
    print(f"  - branches : {tdma_solver.NumBranches()}")
    print(f"  - wall time: {tdma_solver.WallTime()}s")

    print(f"Model statistics:\n{tdma_model.ModelStats()}")

    print(f"Model HasObjective: {tdma_model.HasObjective()}")

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print("Solution:")
        # Create one list of assigned tasks per machine.
        assigned_jobs = collections.defaultdict(list)
        for job_id, job in zip(vl_ids, jobs_data):
            for task_id, task in enumerate(job):
                machine = task[0]
                assigned_jobs[machine].append(
                    assigned_task_type(
                        start=tdma_solver.Value(all_tasks[job_id, task_id].start),
                        end=tdma_solver.Value(all_tasks[job_id, task_id].end),
                        job=job_id,
                        index=task_id,
                        duration=task[1],
                    )
                )
        print(assigned_jobs)
        # Create per machine output lines.
        output: str = ""
        for machine in node_ids:
            # Sort by starting time.
            assigned_jobs[machine].sort()
            sol_line_tasks: str = "Machine " + str(machine) + ": "
            sol_line: str = "           "

            for assigned_task in assigned_jobs[machine]:
                name = f"job_{assigned_task.job}_task_{assigned_task.index}"
                # add spaces to output to align columns.
                sol_line_tasks += f"{name:15}"

                start = assigned_task.start
                duration = assigned_task.duration
                sol_tmp = f"[{start},{start + assigned_task.end}]"
                # add spaces to output to align columns.
                sol_line += f"{sol_tmp:15}"

            sol_line += "\n"
            sol_line_tasks += "\n"
            output += sol_line_tasks
            output += sol_line

        # Finally print the solution found.
        print(f"Optimal Schedule Length: {tdma_solver.ObjectiveValue()}")
        print(output)
    else:
        print("No solution found.")
        print("Solver status code:", status, ", name: ", status_name)

    if not status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        logging.warning(
            "No feasible or optimal solution found for TDMA schedule. Exiting program!"
        )
        sys.exit(1)

    def export_schedule(solver_results, assigned_slots, min_gbt, output_schema):
        """Export optimized schedule according to JSON output schema

        :param solver_results: OR tools solver object
        :param assigned_slots: Slots assigned to nodes
        :param min_gbt: Minimum GBT value
        :param output_schema: JSON output schema to validate against
        :return json_output: Schedule represented as JSON object
        """
        json_output = {
            "cycle_time": solver_results.ObjectiveValue(),
            "slots": [],
        }
        slots_array = json_output["slots"]

        for machine_slots in assigned_slots.items():
            node_name = machine_slots[0]
            node_slots = machine_slots[1]
            for slot in node_slots:
                slots_array.append(
                    {
                        "virtual_links": [slot.job],
                        "is_deterministic": True,
                        "nap_interface": node_name,
                        "start": slot.start,
                        "end": slot.end - min_gbt,
                    }
                )
        # Validate output against output schema
        jsonschema.validate(instance=json_output, schema=output_schema)

        print(json_output)
        return json_output

    schedule_output = export_schedule(
        tdma_solver, assigned_jobs, minimum_guard_width, schema_output_scheduler
    )
    with open(
        os.path.join(output_folder_path, "schedule_output.json"), "w", encoding="utf-8"
    ) as output_file:
        json.dump(schedule_output, output_file, indent=2)

    # Export nap configuration to JSON
    def export_config(
        solver_results,
        assigned_slots,
        min_gbt,
        input_json,
        config_schema,
        nap_config=False,
    ):
        json_output = {"cycle_time": solver_results.ObjectiveValue(), "naps": []}

        # Get inner domain interfaces for each nap
        nap_to_inner_interfaces = collections.defaultdict(list)
        inner_interfaces_to_nap = collections.defaultdict(list)
        for link in input_json["inner_domain_links"]:
            for interface in link["interface_list"]:
                nap_to_inner_interfaces[interface["nap_id"]].append(
                    interface["interface_id"]
                )
                inner_interfaces_to_nap[interface["interface_id"]].append(
                    interface["nap_id"]
                )

        # Get outer domain interfaces for each nap
        nap_to_outer_interfaces = collections.defaultdict(list)
        outer_interfaces_to_nap = collections.defaultdict(list)
        outer_interfaces_to_type = {}
        for interface in input_json["outer_domain_interfaces"]:
            outer_domain_label = (interface["nap_id"], interface["interface_id"])
            nap_to_outer_interfaces[interface["nap_id"]].append(
                {
                    "interface_id": outer_domain_label,
                    "interface_type": interface["interface_type"],
                }
            )
            outer_interfaces_to_nap[outer_domain_label].append(interface["nap_id"])
            outer_interfaces_to_type[outer_domain_label] = interface["interface_type"]

        # Get VLs which have a target and/or source in the outer domain
        outer_to_inner_mapped_vls = collections.defaultdict(list)
        inner_to_outer_mapped_vls = collections.defaultdict(list)
        for vl_id, current_vl in all_vls.items():
            # current_vl = all_vls[vl_id]
            current_path = used_paths[vl_id]
            if current_vl["source"] in outer_domain_ids:
                # outer_to_inner_mapped_vls[vl["source"]].append(vl)
                # Find connected inner domain link
                current_nap = outer_interfaces_to_nap[current_vl["source"]][0]
                current_interfaces = nap_to_inner_interfaces[current_nap]
                inner_domain_link_id = None
                for connection in current_path:
                    if connection[0] in current_interfaces:
                        inner_domain_link_id = connection[0]
                        outer_inner_mapping = {
                            "inner_domain_link_id": inner_domain_link_id,
                            "vl_id": vl_id,
                            "if_ch_number": current_vl["interface_channel"],
                            "if_number": current_vl["source"][1],
                            "if_type": outer_interfaces_to_type[current_vl["source"]],
                        }
                        outer_to_inner_mapped_vls[current_nap].append(
                            outer_inner_mapping
                        )
                        break
            for t in current_vl["target"]:
                # Skip target if it isn't an outer domain interface
                if t not in outer_domain_ids:
                    continue
                # inner_to_outer_mapped_vls[t].append(current_vl)
                current_nap = outer_interfaces_to_nap[t][0]
                current_interfaces = nap_to_inner_interfaces[current_nap]
                for connection in current_path:
                    # Check if the target of the connection is the current nap
                    if connection[1] in current_interfaces:
                        # Check if outer domain connection is last hop of this VL (leaf of the spanning tree)
                        last = not bool(
                            [a for a in current_path if a[0] in current_interfaces]
                        )

                        # For VL with local destination check last
                        if current_vl["local_destination"]:
                            last = True

                        inner_domain_link_id = connection[1]
                        # Check if redundant VL already has an entry
                        redundant_mapping = []
                        if current_vl["redundant_to"]:
                            redundant_vl_ids = current_vl["redundant_to"]
                            redundant_mapping = [
                                i
                                for i in inner_to_outer_mapped_vls[current_nap]
                                if i["vl_id"][0] in redundant_vl_ids
                            ]
                        if redundant_mapping:
                            redundant_mapping = redundant_mapping[0]
                            redundant_mapping["inner_domain_link_id"].append(
                                inner_domain_link_id
                            )
                            redundant_mapping["vl_id"].append(vl_id)
                            redundant_mapping["last"].append(last)
                            break

                        inner_outer_mapping = {
                            "inner_domain_link_id": [inner_domain_link_id],
                            "vl_id": [vl_id],
                            "if_ch_number": current_vl["interface_channel"],
                            "if_number": t[1],
                            "if_type": outer_interfaces_to_type[t],
                            "last": [last],
                        }
                        if "deduplication_method" in current_vl:
                            inner_outer_mapping["deduplication_method"] = current_vl[
                                "deduplication_method"
                            ]
                        if "deduplication_source" in current_vl:
                            inner_outer_mapping["deduplication_source"] = current_vl[
                                "deduplication_source"
                            ]
                        inner_to_outer_mapped_vls[current_nap].append(
                            inner_outer_mapping
                        )
                        break

        for nap_id in nap_ids:
            json_output["naps"].append(
                {
                    "nap_id": nap_id,
                    "vl_mapping_inner_to_outer": inner_to_outer_mapped_vls[nap_id],
                    "vl_mapping_outer_to_inner": outer_to_inner_mapped_vls[nap_id],
                    "tdma_slots": [],
                }
            )

            tdma_slots = json_output["naps"][-1]["tdma_slots"]
            # Get inner domain interfaces connected to the NAP
            for interface in nap_to_inner_interfaces[nap_id]:
                # Get slots for each interface
                for slot in assigned_slots[interface]:
                    # Skip inner domain forwarding slots for NAP configuration
                    if nap_config:
                        outer_to_inner_mappings = [
                            m["vl_id"] for m in outer_to_inner_mapped_vls[nap_id]
                        ]
                        if slot.job == 577 and nap_id == "NAP30":
                            pass
                        if (
                            slot.job not in outer_to_inner_mappings
                            and all_vls[slot.job]["source"] != nap_id
                        ):
                            print("Skipped inner domain forwarding slot!")
                            continue
                    tdma_slots.append(
                        {
                            "virtual_links": [slot.job],
                            "is_deterministic": True,
                            "inner_domain_link_id": interface,
                            "start": slot.start,
                            "end": slot.end - min_gbt,
                            "local_destination": all_vls[slot.job]["local_destination"],
                        }
                    )

            # Add time sync priority if exists
            if nap_id in time_sync_priorities_dict:
                json_output["naps"][-1]["time_sync_priority"] = (
                    time_sync_priorities_dict[nap_id]
                )
        # print(json_output)

        # Validate output against output schema
        jsonschema.validate(instance=json_output, schema=config_schema)

        return json_output

    # logging.info("Export config")
    config_output = export_config(
        tdma_solver,
        assigned_jobs,
        minimum_guard_width,
        input_json,
        schema_output_config,
    )

    with open(
        os.path.join(output_folder_path, "config_output.json"), "w", encoding="utf-8"
    ) as output_file:
        json.dump(config_output, output_file, indent=2)

    # Export NAP config

    nap_config_output = export_config(
        tdma_solver,
        assigned_jobs,
        minimum_guard_width,
        input_json,
        schema_output_config,
        nap_config=True,
    )

    with open(
        os.path.join(output_folder_path, "nap_config_output.json"),
        "w",
        encoding="utf-8",
    ) as output_file:
        json.dump(nap_config_output, output_file, indent=2)

    # logging.info("Exporting pgf gantt diagram")
    # print_gantt(jobs_data, vl_ids, node_ids, assigned_jobs, output_directory_name=output_folder_name)

    # Create plantUML gantt diagram
    logging.info("Exporting plantUML gantt diagram")
    export_plantuml(
        vl_ids,
        node_ids,
        assigned_jobs,
        tdma_solver.ObjectiveValue(),
        output_directory_name=output_folder_path,
    )

    # Create plotly interactive schedule diagram
    logging.info("Exporting interactive network schedule diagram")
    print_schedule_in_graph(
        network_graph,
        tdma_solver.ObjectiveValue(),
        assigned_jobs,
        output_directory_name=output_folder_path,
    )

    # Create plotly gantt diagram
    logging.info("Exporting interactive gantt diagram")
    plotly_gantt(
        assigned_jobs,
        tdma_solver.ObjectiveValue(),
        output_directory_name=output_folder_path,
    )


if __name__ == "__main__":
    main()
