"""Verifier for the TDMA schedule"""

# Imports
import collections
import json
import logging
import sys
import os
import argparse
import jsonschema


def verify_slot_end_gbt(
    all_interface_ids, interface_to_slots_dict, network_cycle_time, network_min_gbt
):
    """Verify the correct end of slots in regard to cycle time and minimum gbt

    :param all_interface_ids: List of all interface IDs used in scheduler
    :param interface_to_slots_dict: Dictionary assigning a list of slots to an interface id
    :param network_cycle_time: Cycle time of the network
    :param network_min_gbt: Minimum GBT of the network

    :return: list of tuples with error code and error message. Empty if verification is successful.
    """
    error_list = []
    for interface_id_current in all_interface_ids:
        # Check if slots overlap and the min gbt is kept
        slots = interface_to_slots_dict[interface_id_current]
        logging.info(f"Slots of interface {interface_id_current}: {slots}")
        for slot_index, slot_current in enumerate(slots):
            # print(slot_index, slot)
            # Check if slot ends before cycle time
            if not slot_current["end"] <= network_cycle_time:
                error_message = f"Slot {slot_index} ended after cycle time!"
                logging.error(error_message)
                error_list.append((5, error_message))

            # Check for overlap and min gbt for each but the last slot of the interface
            if slot_index < len(slots) - 1:
                if (
                    not slot_current["end"] + network_min_gbt
                    <= slots[slot_index + 1]["start"]
                ):
                    error_message = f"Slot {slot_index} overlaps with next slot!"
                    logging.error(error_message)
                    error_list.append((6, error_message))
            # Check for last slot of the interface
            else:
                if (
                    not network_min_gbt
                    <= network_cycle_time - slot_current["end"] + slots[0]["start"]
                ):
                    error_message = (
                        f"Last slot {slot_index} exceeds cycle time with min GBT!"
                    )
                    logging.error(error_message)
                    error_list.append((7, error_message))
    return error_list


def check_best_effort_slot_width(all_slots_list, vl_id_to_vl_dict):
    """Check that all best effort slots are wide enough for all assigned VLs, warn if not the case

    :param all_slots_list: List of all slots
    :param vl_id_to_vl_dict: Dictionary assigning a VL IDs to VL information from the input file

    :return: list of tuples with error code and error message. Empty if verification is successful.
    """
    error_list = []
    for slot_current in all_slots_list:
        # Sort out deterministic slots
        if slot_current["is_deterministic"]:
            continue
        assigned_virtual_links = slot_current["virtual_links"]
        # Calculate the sum of all virtual links assigned to this slot
        max_width = sum(
            vl_id_to_vl_dict[a]["data_size"] for a in assigned_virtual_links
        )
        if max_width > slot_current["end"] - slot_current["start"]:
            error_message = f"{slot_current} max width of assigned VLs is greater then the slot width!"
            logging.warning(error_message)
            error_list.append((-1, error_message))
    return error_list


def verify_targets_reachable_slots_available(
    virtual_links_list,
    virtual_link_to_slots_dict,
    nap_interface_id_to_nap_interface_dict,
    nap_id_to_outer_domain_interface_ids,
    common_hop_latency,
):
    """Verify for each deterministic virtual link if all targets are reachable and have slots
    available

    :param virtual_links_list: List of all virtual links
    :param virtual_link_to_slots_dict: Dictionary assigning virutal link ID to a list of assigned slots
    :param nap_interface_id_to_nap_interface_dict: Dictionary assigning a dictionary of NAP interface information
        to a NAP interface id
    :param nap_id_to_outer_domain_interface_ids: Dictionary assigning a list of outer domain interface ID to a NAP
        interface id
    :param common_hop_latency: Common hop latency value

    :return: list of tuples with error code and error message. Empty if verification is successful.
    """

    def bfs(graph, v, bfs_nap_interface_id_to_nap_interface, outer_domain_ids):
        """Helper function to use breath first search to
        traverse network graph and collect latency values

        :param graph: Network graph as adjacency list
        :param v: Start vertice
        :param bfs_nap_interface_id_to_nap_interface: Dictionary assigning a NAP interface information to a NAP
            interface ID
        :param outer_domain_ids: List of outer domain IDs in tuples of the form (NAP ID, Outer Domain ID)

        :return: Two object, first a list of all nodes, second a dictionary with IDs to latency values
        """

        all_nodes = []
        q = []
        latencies_dict = {}
        q.append(v)
        latencies_dict[v] = 0
        while q:
            v = q.pop(0)
            all_nodes.append(v)
            for n in graph[v]:
                if n[0] not in q and n[0] not in all_nodes:
                    q.append(n[0])
                    if n[0] in outer_domain_ids:
                        latencies_dict[n[0]] = latencies_dict[v]
                    else:
                        latencies_dict[n[0]] = (
                            latencies_dict[v]
                            + bfs_nap_interface_id_to_nap_interface[
                                n[1]["nap_interface"]
                            ]["latency"]
                        )
        return all_nodes, latencies_dict

    error_list = []

    for vl_current in virtual_links_list:
        for vl_id in vl_current["id"]:
            assigned_slots = virtual_link_to_slots_dict[vl_id]
            # Create adjacency list from slots
            adjacency_list = collections.defaultdict(list)
            for slot_current in assigned_slots:
                nap_interface_id = slot_current["nap_interface"]
                nap_interface = nap_interface_id_to_nap_interface_dict[nap_interface_id]
                adjacency_list[nap_interface["nap"]].append(
                    (nap_interface["connected_nap"], slot_current)
                )
                for outer_domain_id in nap_id_to_outer_domain_interface_ids[
                    nap_interface["nap"]
                ]:
                    outer_domain_label = (nap_interface["nap"], outer_domain_id)
                    adjacency_list[outer_domain_label].append(
                        (outer_domain_id, slot_current)
                    )
                    adjacency_list[outer_domain_label].append(
                        (nap_interface["nap"], slot_current)
                    )
                for outer_domain_id in nap_id_to_outer_domain_interface_ids[
                    nap_interface["connected_nap"]
                ]:
                    outer_domain_label = (
                        nap_interface["connected_nap"],
                        outer_domain_id,
                    )
                    adjacency_list[nap_interface["connected_nap"]].append(
                        (outer_domain_label, slot_current)
                    )
                    adjacency_list[outer_domain_label].append(
                        (nap_interface["connected_nap"], slot_current)
                    )

                # Check if the width of the slot is wide enough
                retransmission_time = (
                    vl_current["data_size"]
                    if vl_current["allow_retransmissions"]
                    else 0
                )
                if not (
                    slot_current["end"] - slot_current["start"]
                    >= vl_current["data_size"] + retransmission_time
                ):
                    error_message = f"Width of slot {slot_current} not wide enough!"
                    logging.error(error_message)
                    error_list.append((8, error_message))
            # print("al:", adjacency_list)
            # Create list of all outer domain IDs
            outer_domain_ids = [
                (n, b)
                for n, o in nap_id_to_outer_domain_interface_ids.items()
                for b in o
            ]

            # Check if source of VL is an outer domain interface and change source label accordingly
            if (
                "interface_id" in vl_current["source_nap"]
                and vl_current["source_nap"]["interface_id"] != ""
            ):
                source_label = (
                    vl_current["source_nap"]["nap_id"],
                    vl_current["source_nap"]["interface_id"],
                )
            else:
                source_label = vl_current["source_nap"]["nap_id"]

            reachable_nodes, latencies = bfs(
                adjacency_list,
                source_label,
                nap_interface_id_to_nap_interface_dict,
                outer_domain_ids,
            )
            # print(reachable_nodes)

            # Verify that the common hop latency is considered for successive slots
            logging.debug(f"Checking common hop latency for VL {vl_id}")
            next_naps = [source_label]
            while next_naps:
                current_nap = next_naps.pop()
                hops = adjacency_list[current_nap]
                for hop in hops:
                    # Ignore outer domain hops
                    if hop[0] in outer_domain_ids:
                        continue
                    current_start = hop[1]["start"]
                    next_naps.append(hop[0])
                    # Don't check common hop latency if current NAP is outer domain
                    if current_nap in outer_domain_ids:
                        continue
                    # Create list of next hops without outer domain ID targets
                    next_hops = [
                        a
                        for a in adjacency_list[hop[0]]
                        if a[0] not in outer_domain_ids
                    ]
                    # Ignore last hop for VLs with local destination
                    if (
                        vl_current["local_destination"]
                        and next_hops
                        and next_hops[0][0] in source_label
                    ):
                        next_naps = []
                        break
                    # Create list of hops that violate the common hop latency
                    violations = [
                        a
                        for a in next_hops
                        if a[1]["start"] != current_start + common_hop_latency
                    ]
                    for violation in violations:
                        error_message = (
                            f"Common hop latency of {common_hop_latency} disregarded between NAP "
                            f"'{current_nap}', '{hop[0]}' and '{violation[0]}' for VL {vl_id}!"
                        )
                        logging.error(error_message)
                        error_list.append((11, error_message))

            # Check if all target naps are in the reachable nodes within the required maximum latency
            for target in vl_current["target_naps"]:
                if "interface_id" in target and target["interface_id"] != "":
                    target_label = (target["nap_id"], target["interface_id"])
                else:
                    target_label = target["nap_id"]
                if target_label not in reachable_nodes:
                    error_message = f"Target {target_label} not reachable!"
                    logging.error(error_message)
                    error_list.append((9, error_message))
                if not latencies[target_label] <= vl_current["max_allowed_latency"]:
                    error_message = (
                        f"Latency {target_label} exceeds max allowed latency!"
                    )
                    logging.error(error_message)
                    error_list.append((10, error_message))
    return error_list


def verify_redundancy(redundant_virtual_links_list, virtual_link_to_slots_dict):
    """Verify that redundant VLs don't use the same edges for their paths

    :param redundant_virtual_links_list: list of lists of virtual links redundant to each other
    :param virtual_link_to_slots_dict: dictionary of virtual links to list of assigned slots

    :return: list of tuples with error code and error message. Empty if verification is successful.
    """
    error_list = []
    for vl_group in redundant_virtual_links_list:
        used_interfaces = []
        # Go over each VL in the redundant VL group
        for vl in vl_group:
            # Look up slots used by this VL
            for slot in virtual_link_to_slots_dict[vl]:
                if slot["nap_interface"] in used_interfaces:
                    error_message = f"Redundant VL {vl} uses the same interface!"
                    logging.error(error_message)
                    error_list.append((12, error_message))
                used_interfaces.append(slot["nap_interface"])
    return error_list


def verify_vl_active(vl_ids_inactive, slots):
    """Verify that no VLs are scheduled that are not marked active

    :param vl_ids_inactive: List of VLs that are marked inactive from the scheduler input
    :param slots: List of all scheduled slots from the scheduler output

    :return: list of tuples with error code and error message. Empty if verification is successful.
    """

    error_list = []
    for slot in slots:
        for vl_id in slot["virtual_links"]:
            if vl_id in vl_ids_inactive:
                error_message = f"VL {vl_id} is marked as inactive, but was scheduled in slot {slot}"
                error_list.append((12, error_message))
    return error_list


def verify_no_outer_domain_source_branching(
    virtual_links, virtual_link_to_slots, nap_interface_id_to_nap_interface
):
    """Verify that VLs that originate in the outer domain do not branch on the first NAP

    :param virtual_links: List of VLs that are scheduled from the scheduler input
    :param virtual_link_to_slots: Dict with VL IDs as keys and slots as values
    :param nap_interface_id_to_nap_interface: Dict with interface IDs as keys and nap interface information as values

    :return: list of tuples with error code and error message. Empty if verification is successful.
    """
    error_list = []

    # Check for virtual links with source in the outer domain
    virtual_links_source_outer_domain = [
        v
        for v in virtual_links
        if "interface_id" in v["source_nap"] and v["source_nap"]["interface_id"] != ""
    ]
    for virtual_link in virtual_links_source_outer_domain:
        source_nap = virtual_link["source_nap"]["nap_id"]
        # Get all inner domain interfaces connected to the source nap
        connected_interfaces = [
            i
            for i, n in nap_interface_id_to_nap_interface.items()
            if n["nap"] == source_nap
            and n != virtual_link["source_nap"]["interface_id"]
        ]
        # Iterate over all VL IDs (multiple if redundant)
        for vl_id in virtual_link["id"]:
            # Get list of used connected interfaces
            used_interfaces = {
                s["nap_interface"]
                for s in virtual_link_to_slots[vl_id]
                if s["nap_interface"] in connected_interfaces
            }
            if len(used_interfaces) > 1:
                error_message = f"VL {vl_id} has a source in the outer domain but branches on source NAP {source_nap}!"
                error_list.append((13, error_message))
            # for slot in virtual_link_to_slots[vl_id]:

    return error_list


def verify_inner_to_outer_mapping(
    vl_id_to_outer_domain_id,
    vl_id_to_channel,
    vl_id_to_deduplication,
    outer_domain_id_to_nap_id,
    nap_id_to_mappings,
    nap_id_to_egress_slots,
    nap_id_to_ingress_slots,
):
    """Verify the existence of a correct inner domain to outer domain mapping
    for each VL with one or more targets in the outer domain.

    :param vl_id_to_outer_domain_id: Dictionary with VL IDs of VLs with outer domain interface targets.
        Items are lists of outer domain IDs.
    :param vl_id_to_channel: Dictionary mapping all VL IDs to their channel.
    :param vl_id_to_deduplication: Dictionary mapping all VL IDs to their deduplication method and source if any.
    :param outer_domain_id_to_nap_id: Dictionary mapping domain IDs to their connected NAP ID and interface type.
    :param nap_id_to_mappings: Dictionary with NAP IDs as key with a list of each inner to outer mapping
        from the config as elements.
    :param nap_id_to_egress_slots: Dictionary with NAP IDs as key with a list of egress slots
        from the config to each of those naps.
    :param nap_id_to_ingress_slots: Dictionary with NAP IDs as key with a list of ingress slots
        from the config to each of those naps.

    :return: list of tuples with error code and error message. Empty if verification is successful.
    """
    error_list = []
    # Check for each VL with outer domain targets
    for vl_id, targets in vl_id_to_outer_domain_id.items():
        logging.debug(
            f"Checking inner to outer mapping for VL {vl_id} and targets {targets}"
        )
        # Check for each target outer domain interface in the targets list
        for target in targets:
            connected_nap = outer_domain_id_to_nap_id[target][0]
            if connected_nap in nap_id_to_mappings.keys():
                mappings = nap_id_to_mappings[connected_nap]
            else:
                mappings = []
            correct_mapping = None
            for mapping in mappings:
                if (
                    vl_id in mapping["vl_id"]
                    and (connected_nap, mapping["if_number"]) == target
                ):
                    # Check if multiple inner to outer mappings exist for the same VL
                    if correct_mapping is not None:
                        error_message = f"Multiple mappings for VL {vl_id} on NAP '{connected_nap}' found!"
                        logging.error(error_message)
                        error_list.append((50, error_message))
                    correct_mapping = mapping
            if correct_mapping is None:
                error_message = f"No inner to outer mapping found for VL {vl_id} on NAP '{connected_nap}'!"
                logging.error(error_message)
                error_list.append((57, error_message))
                return error_list
            logging.info(
                f"Correct mapping found for VL {vl_id} on NAP '{connected_nap}'"
            )
            # Check mapping channel number against input
            if correct_mapping["if_ch_number"] != vl_id_to_channel[vl_id]:
                error_message = (
                    f"Channel number {correct_mapping['if_ch_number']} for mapping is different "
                    f"from VL channel number {vl_id_to_channel[vl_id]} in schedule input!"
                )
                logging.error(error_message)
                error_list.append((51, error_message))
            # Check interface type
            if correct_mapping["if_type"] != outer_domain_id_to_nap_id[target][1]:
                error_message = (
                    f"Interface type {correct_mapping['if_type']} for mapping is different from "
                    f"VL interface type {outer_domain_id_to_nap_id[target][1]} in schedule input!"
                )
                logging.error(error_message)
                error_list.append((52, error_message))
            # Check inner domain link ID
            used_ingress_link = [
                a
                for a in nap_id_to_ingress_slots[connected_nap]
                if vl_id in a["virtual_links"]
            ]
            if len(used_ingress_link) > 1:
                error_message = (
                    f"VL {vl_id} has multiple ingress slots in NAP '{connected_nap}'!"
                )
                logging.error(error_message)
                error_list.append((53, error_message))
            used_ingress_link = used_ingress_link[0]
            if (
                used_ingress_link["ingress_interface"]
                != correct_mapping["inner_domain_link_id"][
                    correct_mapping["vl_id"].index(vl_id)
                ]
            ):
                error_message = (
                    f"Mapping for VL {vl_id} contains different "
                    f"inner domain link ID from found ingress slot!"
                )
                logging.error(error_message)
                error_list.append((54, error_message))
            # Check mapping 'last' parameter
            egress_slots = [
                e
                for e in nap_id_to_egress_slots[connected_nap]
                if vl_id in e["virtual_links"]
            ]
            if (
                correct_mapping["last"][correct_mapping["vl_id"].index(vl_id)]
                and len(egress_slots) > 0
            ):
                error_message = (
                    f"Mapping for VL {vl_id} has 'last' set true "
                    f"but connected NAP has egress slots for the same VL!"
                )
                logging.error(error_message)
                error_list.append((55, error_message))
            if (
                not correct_mapping["last"][correct_mapping["vl_id"].index(vl_id)]
                and len(egress_slots) == 0
            ):
                error_message = (
                    f"Mapping for VL {vl_id} has 'last' set false "
                    f"but connected NAP has no egress slots for the same VL!"
                )
                logging.error(error_message)
                error_list.append((56, error_message))
            # Check deduplication parameters
            if len(correct_mapping["vl_id"]) > 1:
                if not (
                    correct_mapping["deduplication_method"]
                    == vl_id_to_deduplication[vl_id]["deduplication_method"]
                ):
                    error_message = f"Mapping for VL {vl_id} has different deduplication method/source to input"
                    logging.error(error_message)
                    error_list.append((58, error_message))
                if vl_id_to_deduplication[vl_id][
                    "deduplication_method"
                ] == "static" and (
                    "deduplication_source" not in correct_mapping
                    or correct_mapping["deduplication_source"]
                    != vl_id_to_deduplication[vl_id]["deduplication_source"]
                ):
                    error_message = f"Mapping for VL {vl_id} has different deduplication method/source to input"
                    logging.error(error_message)
                    error_list.append((58, error_message))

    return error_list


def verify_outer_to_inner_mapping(
    vl_id_to_outer_domain_id,
    vl_id_to_channel,
    outer_domain_id_to_nap_id,
    nap_id_to_mappings,
    nap_id_to_egress_slots,
):
    """Verify the existence of a correct outer domain to inner domain mapping
    for each VL with a source in the outer domain.

    :param vl_id_to_outer_domain_id: Dictionary with VL IDs of VLs with an outer domain interface source.
        Items are domain IDs.
    :param vl_id_to_channel: Dictionary mapping all VL IDs to their channel.
    :param outer_domain_id_to_nap_id: Dictionary mapping domain IDs to their connected NAP ID and interface type.
    :param nap_id_to_mappings: Dictionary with NAP IDs as key with a list of each outer to inner mapping
        from the config as elements.
    :param nap_id_to_egress_slots: Dictionary with NAP IDs as key with a list of egress slots
        from the config to each of those naps.

    :return: list of tuples with error code and error message. Empty if verification is successful.
    """
    error_list = []

    # Check for each VL with an outer domain source
    for vl_id, source in vl_id_to_outer_domain_id.items():
        source_label = source
        logging.debug(
            f"Checking outer to inner mapping for VL {vl_id} and source {source_label}"
        )
        connected_nap = outer_domain_id_to_nap_id[source_label][0]
        if connected_nap in nap_id_to_mappings.keys():
            mappings = nap_id_to_mappings[connected_nap]
        else:
            mappings = []
        correct_mapping = None
        for mapping in mappings:
            if (
                vl_id == mapping["vl_id"]
                and (connected_nap, mapping["if_number"]) == source_label
            ):
                # Check if multiple inner to outer mappings exist for the same VL
                if correct_mapping is not None:
                    error_message = f"Multiple mappings for VL {vl_id} on NAP '{connected_nap}' found!"
                    logging.error(error_message)
                    error_list.append((80, error_message))
                correct_mapping = mapping
        if correct_mapping is None:
            error_message = f"No outer to inner mapping found for VL {vl_id} on NAP '{connected_nap}'!"
            logging.error(error_message)
            error_list.append((85, error_message))
            return error_list
        logging.info(f"Correct mapping found for VL {vl_id} on NAP '{connected_nap}'")
        # Check mapping channel number against input
        if correct_mapping["if_ch_number"] != vl_id_to_channel[vl_id]:
            error_message = (
                f"Channel number {correct_mapping['if_ch_number']} for mapping is different "
                f"from VL channel number {vl_id_to_channel[vl_id]} in schedule input!"
            )
            logging.error(error_message)
            error_list.append((81, error_message))
        # Check interface type
        if correct_mapping["if_type"] != outer_domain_id_to_nap_id[source_label][1]:
            error_message = (
                f"Interface type {correct_mapping['if_type']} for mapping is different from "
                f"VL interface type {outer_domain_id_to_nap_id[source_label][1]} in schedule input!"
            )
            logging.error(error_message)
            error_list.append((82, error_message))
        # Check inner domain link ID
        used_egress_link = [
            a
            for a in nap_id_to_egress_slots[connected_nap]
            if vl_id in a["virtual_links"]
        ]
        if len(used_egress_link) > 1:
            error_message = (
                f"VL {vl_id} has multiple egress slots in NAP '{connected_nap}'!"
            )
            logging.error(error_message)
            error_list.append((83, error_message))
        used_egress_link = used_egress_link[0]
        if used_egress_link["nap_interface"] != correct_mapping["inner_domain_link_id"]:
            error_message = (
                f"Mapping for VL {vl_id} contains different "
                f"inner domain link ID from found egress slot!"
            )
            logging.error(error_message)
            error_list.append((84, error_message))

    return error_list


def source_target_to_label(source_targets):
    """Get label to VL source or target

    :param source_target: VL source or target dict or list of source or target dict

    :return: NAP id or NAP id with interface id tuple if outer domain
    """

    def single_label(nap_interface_dict):
        """Helper function to create one label from nap and interface id

        :param nap_interface_dict: NAP interface dict
        :return: NAP ID if input is not interface else a tuple with NAP ID and interface ID
        """
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


def main():
    """Verifier main function"""

    # Define command line arguments
    parser = argparse.ArgumentParser(
        prog="verifier",
        description="Verifier for TDMA schedule and config",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "output-scheduler",
        help="scheduler output file",
        nargs="?",
        default="verifier_output_schedule_example.json",
    )
    parser.add_argument(
        "-o",
        "--output-schema",
        help="output file schema",
        default="schema_output_scheduler.json",
        required=False,
    )
    parser.add_argument(
        "input-scheduler",
        help="scheduler input file",
        nargs="?",
        default="verifier_input_example.json",
    )
    parser.add_argument(
        "-i",
        "--input-schema",
        help="input file schema",
        default="schema_input_scheduler.json",
        required=False,
    )
    parser.add_argument(
        "-c",
        "--config",
        help="input file and input schema is interpreted; compatibility to old input file format",
        action="store_true",
    )
    parser.add_argument(
        "-l",
        "--log-level",
        help="log level",
        choices=["debug", "info", "warning", "warn", "error", "fatal", "critical"],
        default="info",
    )
    # parser.print_help()

    # Read command line inputs
    args = vars(parser.parse_args())
    # print("args:", args)
    output_file_name = args["output-scheduler"]
    input_file_name = args["input-scheduler"]
    output_schema_name = args["output_schema"]
    input_schema_name = args["input_schema"]
    config = args["config"]
    log_level = args["log_level"]

    # Configure logging
    logging.basicConfig(
        format="%(asctime)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
        level=logging.getLevelNamesMapping()[log_level.upper()],
    )

    logging.info(f"Input file name: {input_file_name}")
    logging.info(f"Output file name: {output_file_name}")
    logging.info(f"Input file schema: {input_schema_name}")
    logging.info(f"Output file schema: {output_schema_name}")

    # Read ouput and input files
    script_dir = os.path.dirname(__file__)

    with open(
        os.path.join(script_dir, output_file_name), "r", encoding="utf-8"
    ) as output_file:
        output_example = json.load(output_file)

    with open(
        os.path.join(script_dir, input_file_name), "r", encoding="utf-8"
    ) as input_file:
        input_example = json.load(input_file)

    # List for errors in the form (ERRORCODE, MESSAGE)
    main_error_list = []

    # Read scheduler output json schema file
    with open(
        os.path.join(script_dir, output_schema_name), encoding="utf-8"
    ) as schema_output_scheduler_file:
        schema_output_scheduler = json.load(schema_output_scheduler_file)

    # Slot file input example
    logging.debug(f"Input file header: {list(schema_output_scheduler.keys())}")

    # Validate slot input file
    try:
        jsonschema.validate(instance=output_example, schema=schema_output_scheduler)
    except jsonschema.exceptions.SchemaError as e:
        logging.error(e)
        main_error_list.append((1, e))
    except jsonschema.exceptions.ValidationError as e:
        logging.error(e)
        main_error_list.append((2, e))

    # Read scheduler input json schema file
    with open(
        os.path.join(script_dir, input_schema_name), encoding="utf-8"
    ) as schema_input_scheduler_file:
        # sched_int_in_3
        schema_input_scheduler = json.load(schema_input_scheduler_file)

    # Validate input parameter file
    try:
        jsonschema.validate(instance=input_example, schema=schema_input_scheduler)
    except jsonschema.exceptions.SchemaError as e:
        logging.error(e)
        main_error_list.append((3, e))
    except jsonschema.exceptions.ValidationError as e:
        logging.error(e)
        main_error_list.append((4, e))

    # Get min gbt value
    min_gbt: int = input_example["min_gbt"]

    # Get common hop latency value
    common_hop_latency = input_example["common_latency_value"]

    # Get all virtual links split by vl_active true or false
    virtual_links = [a for a in input_example["virtual_links"] if a["vl_active"]]
    virtual_links_inactive = [
        a for a in input_example["virtual_links"] if not a["vl_active"]
    ]

    # Get all nap interfaces
    # nap_interfaces = input_example["nap_interfaces"]
    domain_links = input_example["inner_domain_links"]

    # Get NAP ID assigned to outer domain interfaces
    outer_domain_interface_id_to_nap_id = {}
    outer_domain_interface_id_to_nap_id_and_interface_type = {}
    outer_domain_ids = []
    for outer_domain in input_example["outer_domain_interfaces"]:
        outer_domain_interface_id_to_nap_id[outer_domain["interface_id"]] = (
            outer_domain["nap_id"]
        )
        outer_domain_interface_id_to_nap_id_and_interface_type[
            (outer_domain["nap_id"], outer_domain["interface_id"])
        ] = (outer_domain["nap_id"], outer_domain["interface_type"])
        outer_domain_ids.append((outer_domain["nap_id"], outer_domain["interface_id"]))

    # Get all outer domain interfaces assigned to each nap
    nap_id_to_outer_domain_interface_ids = collections.defaultdict(list)
    for outer_domain in input_example["outer_domain_interfaces"]:
        nap_id_to_outer_domain_interface_ids[outer_domain["nap_id"]].append(
            outer_domain["interface_id"]
        )

    # Reformat config slot input
    if config:
        output_example["slots"] = [
            s for n in output_example["naps"] for s in n["tdma_slots"]
        ]
        for s in output_example["slots"]:
            s["nap_interface"] = s["inner_domain_link_id"]

    # Get cycle time
    cycle_time: int = output_example["cycle_time"]

    # Get all slots
    all_slots = output_example["slots"]

    # Create dictionary to get virtual links by id
    vl_id_to_vl = {}
    # Create list of redundant VLs
    redundant_vls_list = []
    for vl in virtual_links:
        if len(vl["id"]) > 1:
            redundant_vls_list.append(vl["id"])
            for single_vl in vl["id"]:
                vl_id_to_vl[single_vl] = vl
        else:
            vl_id_to_vl[vl["id"][0]] = vl

    # Create dictionary to get slots assigned to interface
    interface_to_slots = collections.defaultdict(list)
    for slot in all_slots:
        interface_to_slots[slot["nap_interface"]].append(slot)
    logging.debug(f"Slots sorted by interface: {interface_to_slots}")
    interface_ids = list(interface_to_slots.keys())

    # Sort slots by start time
    for interface_id in interface_ids:
        interface_to_slots[interface_id] = sorted(
            interface_to_slots[interface_id], key=lambda a: a["start"]
        )
    logging.debug(f"Slots sorted by interface and start time: {interface_to_slots}")

    # Verify that no inactive VL is scheduled
    main_error_list += verify_vl_active(virtual_links_inactive, all_slots)

    # Verify slot end and gbt
    main_error_list += verify_slot_end_gbt(
        interface_ids, interface_to_slots, cycle_time, min_gbt
    )

    # Check best effort slot width
    main_error_list += check_best_effort_slot_width(all_slots, vl_id_to_vl)

    # Create dictionary to get slots by virtual link id
    virtual_link_to_slots = collections.defaultdict(list)
    for slot in all_slots:
        # Sort out best-effort slots
        if not slot["is_deterministic"]:
            continue
        virtual_link_to_slots[slot["virtual_links"][0]].append(slot)
    logging.debug(f"Slots sorted by virtual link id: {virtual_link_to_slots}")

    # Create dictionary to get nap interfaces by id
    nap_interface_id_to_nap_interface = {}
    for a in domain_links:
        link_one, link_two = a["interface_list"]
        nap_interface_id_to_nap_interface[link_one["interface_id"]] = {
            "id": link_one["interface_id"],
            "nap": link_one["nap_id"],
            "connected_nap": link_two["nap_id"],
            "connected_interface": link_two["interface_id"],
            "latency": a["latency"],
        }
        nap_interface_id_to_nap_interface[link_two["interface_id"]] = {
            "id": link_two["interface_id"],
            "nap": link_two["nap_id"],
            "connected_nap": link_one["nap_id"],
            "connected_interface": link_one["interface_id"],
            "latency": a["latency"],
        }
    # nap_interface_id_to_nap_interface = dict((a["id"], a) for a in nap_interfaces)

    # Verify reachability of targets for each VL
    main_error_list += verify_targets_reachable_slots_available(
        virtual_links,
        virtual_link_to_slots,
        nap_interface_id_to_nap_interface,
        nap_id_to_outer_domain_interface_ids,
        common_hop_latency,
    )

    # Check for redundancy
    main_error_list += verify_redundancy(redundant_vls_list, virtual_link_to_slots)

    # Check for branching of VLs with a source in the outer domain on the source NAP
    main_error_list += verify_no_outer_domain_source_branching(
        virtual_links, virtual_link_to_slots, nap_interface_id_to_nap_interface
    )

    # Check config specific requirements
    if config:
        # Dict VL IDs to target naps
        virtual_link_ids_to_nap_targets = {
            id: source_target_to_label(a["target_naps"])
            for a in virtual_links
            for id in a["id"]
        }
        # Dict of virtual link IDs to outer domain IDs that they have as target
        virtual_links_outer_domain_targets = {
            a: [c for c in b if c in outer_domain_ids]
            for a, b in virtual_link_ids_to_nap_targets.items()
            if [c for c in b if c in outer_domain_ids]
        }
        # Dict of virtual link IDs to outer domain IDs that they have as source
        virtual_links_outer_domain_source = {
            vl_id: source_target_to_label(vl["source_nap"])
            for vl in virtual_links
            for vl_id in vl["id"]
            if source_target_to_label(vl["source_nap"]) in outer_domain_ids
        }
        # Dict of virtual link IDs to channel
        vl_id_to_channel = {a: b["interface_channel"] for a, b in vl_id_to_vl.items()}
        # Dict of virtual link IDs to deduplication parameters if any
        vl_id_to_deduplication_method_source = {
            a: {
                "deduplication_method": b["deduplication_method"],
            }
            for a, b in vl_id_to_vl.items()
            if len(b["id"]) > 1
        }
        # Add deduplication source for VLs with static deduplication method
        for vl_id, vl in vl_id_to_vl.items():
            if len(vl["id"]) > 1 and vl["deduplication_method"] == "static":
                vl_id_to_deduplication_method_source[vl_id]["deduplication_source"] = (
                    vl["deduplication_source"]
                )
        # Dict of NAP IDs to lists of inner to outer mappings
        nap_id_to_inner_to_outer_mapping = {
            a["nap_id"]: a["vl_mapping_inner_to_outer"] for a in output_example["naps"]
        }
        # Dict of NAP IDs to lists of outer to inner mappings
        nap_id_to_outer_to_inner_mapping = {
            a["nap_id"]: a["vl_mapping_outer_to_inner"] for a in output_example["naps"]
        }
        # Dict of NAP IDs to egress slots of this NAP
        nap_id_to_egress_slot = {}
        for nap in output_example["naps"]:
            nap_id = nap["nap_id"]
            egress_slots = []
            for nap_interface in [
                i["id"]
                for i in nap_interface_id_to_nap_interface.values()
                if i["nap"] == nap_id
            ]:
                egress_slots += interface_to_slots[nap_interface]
            nap_id_to_egress_slot[nap_id] = egress_slots
        # Dict of NAP IDs to ingress slots of this NAP
        nap_id_to_ingress_slot = {nap["nap_id"]: [] for nap in output_example["naps"]}
        for interface, connection in nap_interface_id_to_nap_interface.items():
            for slot in interface_to_slots[connection["connected_interface"]]:
                nap_id_to_ingress_slot[connection["nap"]].append(
                    slot | {"ingress_interface": interface}
                )

        # Verify correctness of inner to outer mappings
        main_error_list += verify_inner_to_outer_mapping(
            virtual_links_outer_domain_targets,
            vl_id_to_channel,
            vl_id_to_deduplication_method_source,
            outer_domain_interface_id_to_nap_id_and_interface_type,
            nap_id_to_inner_to_outer_mapping,
            nap_id_to_egress_slot,
            nap_id_to_ingress_slot,
        )
        # Verify correctness of outer to inner mapping
        main_error_list += verify_outer_to_inner_mapping(
            virtual_links_outer_domain_source,
            vl_id_to_channel,
            outer_domain_interface_id_to_nap_id_and_interface_type,
            nap_id_to_outer_to_inner_mapping,
            nap_id_to_egress_slot,
        )


    # Check if error list is empty
    if not main_error_list:
        logging.info("Input schedule is verified!")
        sys.exit(0)
    # Check if only warning were issued
    else:
        for error in main_error_list:
            if error[0] > 0:
                # An error not a warning is found
                logging.error("Input schedule verification failed!")
                sys.exit(error[0])
        # Return the warning
        logging.warning("Input schedule is verified with warning!")
        sys.exit(main_error_list[0][0])


if __name__ == "__main__":
    main()
