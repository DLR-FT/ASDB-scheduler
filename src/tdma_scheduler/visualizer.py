"""TDMA Visualizer
Functions for visualizing TDMA schedules and network graphs
"""

import copy
import datetime
import random
import itertools
import os
from collections import defaultdict
import logging

import matplotlib
import networkx as nx
import pylab as plt
import pandas as pd
from matplotlib import pyplot

import colorcet as cc

# plotly imports
import plotly.graph_objects as go
import plotly.figure_factory as ff
import plotly.express as px


def plot_graph(
    input_graph, output_filename="network.png", output_directory_name="output"
):
    """

    :param input_graph: Networkx graph
    :param output_filename: Name of the PNG output file
    :param output_directory_name: Name of the output directory
    :return:
    """
    # Get node names
    nodes_list = []
    for a in input_graph.nodes:
        if "name" in input_graph.nodes[a]:
            nodes_list.append((a, input_graph.nodes[a]["name"]))
        else:
            nodes_list.append((a, a))
    print("nodes list:", nodes_list)
    node_names = dict(nodes_list)
    # Draw graph
    pos = nx.spring_layout(input_graph, seed=1)
    nx.draw_networkx_nodes(input_graph, pos, node_size=800, linewidths=2.0)
    nx.draw_networkx_labels(input_graph, labels=node_names, pos=pos)
    nx.draw_networkx_edges(input_graph, pos)
    # e = [(0, 1, 0)]
    # e = [(1, 0, 0)]
    # e = [(1, 0, 0), (0, 9, 0), (9, 8, 0), (8, 7, 0), (7, 6, 0), (6, 5, 0)]
    # e = [(1, 0, 0), (0, 9, 0), (9, 8, 0), (8, 7, 0)]
    # e = [(0, 9, 0), (0, 1, 0), (6, 5, 0), (9, 8, 0), (7, 6, 0), (8, 7, 0)]
    # print(G.edges)
    # normal_e = [(u, v, d)  for (u, v, d) in G.edges if (u, v, d) not in e]
    # unnormal_e = [(u, v, d)  for (u, v, d) in G.edges if (u, v, d) in e]
    # nx.draw_networkx_edges(G, pos, edgelist=normal_e)
    # nx.draw_networkx_edges(G, ..
    # pos, edgelist=e, width=3, edge_color="r", arrows=True, arrowstyle="-|>", arrowsize=30)
    plt.savefig(os.path.join(output_directory_name, output_filename))
    plt.close()


def plot_path(
    input_path,
    input_graph,
    output_filename="network.png",
    output_directory_name="output_paths",
):
    """Plot the graph described by the path"""
    # Create directed graph based on input path
    # temp_g = nx.DiGraph()
    # for edge in input_path:
    #     temp_g.add_edge(edge[0], edge[1])
    #
    # pos = nx.spring_layout(temp_g, seed=1)
    # nx.draw_networkx_nodes(temp_g, pos, node_size=800, linewidths=2.0)
    # nx.draw_networkx_labels(temp_g, pos=pos)
    # nx.draw_networkx_edges(temp_g, pos, arrows=True, node_size=800)

    pos = nx.spring_layout(input_graph, seed=1)
    nx.draw_networkx_nodes(input_graph, pos, node_size=800, linewidths=2.0)
    nx.draw_networkx_labels(input_graph, pos=pos)
    nx.draw_networkx_edges(
        input_graph,
        pos,
        edgelist=input_path,
        arrows=True,
        arrowstyle="-|>",
        node_size=800,
    )

    # Create output folder if not exists
    os.makedirs(output_directory_name, exist_ok=True)

    # Save output file
    plt.savefig(os.path.join(output_directory_name, output_filename))
    plt.close()



# visu_int_out_1
def print_gantt(jobs_data, vl_ids, node_ids, assigned_jobs):
    """Print gantt diagram of the TDMA schedule"""
    random_colors = random.sample(
        [pyplot.cm.tab20(b) for b in range(len(jobs_data))], k=len(jobs_data)
    )
    color_to_job = dict(zip(vl_ids, random_colors))
    hatching = ["/", "\\", "|", "-", "+", "x", "o", "O", "."]
    hatching = list(itertools.product(hatching, hatching))
    hatch_to_job = dict(zip(vl_ids, random.sample(hatching, k=len(jobs_data))))
    _, ax = pyplot.subplots()
    node_numbers = enumerate(node_ids)

    ax.set_title("TDMA Schedule")
    ax.set_yticks(list(range(len(node_ids))))
    ax.set_ylim(-1, len(node_ids))
    ax.set_xlabel("Time Units")
    ax.set_ylabel("Interface IDs")
    # Set linewidth for hatching
    matplotlib.rcParams["hatch.linewidth"] = 0.2
    for index_node, node_id in node_numbers:
        # print(f"index: {index}, node_id: {node_id}")
        if assigned_jobs[node_id]:
            for job_current in assigned_jobs[node_id]:
                ax.broken_barh(
                    [(job_current.start, job_current.duration)],
                    (index_node - 0.375, 0.75),
                    facecolors=(color_to_job[job_current.job]),
                    hatch=hatch_to_job[job_current.job],
                )
    ax.set_yticklabels(node_ids)
    pyplot.savefig("tdma_schedule.pgf")
    # pyplot.show()


# visu_int_out_3
def export_plantuml(
    vl_ids,
    node_ids,
    assigned_jobs,
    cycle_time,
    filename="plantuml_output.puml",
    output_directory_name="output",
):
    """
    Export the TDMA schedule as a plantUML text to the console


    :param output_directory_name: Name of the output directory
    """
    # Using glasbey dark colorpalette
    color_to_job = {
        vl_id: cc.b_glasbey_bw_minc_20_maxl_70[i] for i, vl_id in enumerate(vl_ids)
    }
    # print("colors:", color_to_job)
    plantuml_output = """@startgantt
<style>
ganttDiagram {
    task {FontSize 0}
    note {
        LineColor white
        BackGroundColor white
    }
    arrow {
        LineColor gray
        LineStyle 5.0
        LineThickness 2.0
    }
}
</style>
title TDMA Schedule
projectscale daily zoom 2
"""
    # Dict for slots assigned to jobs
    job_to_slots_dict = defaultdict(list)
    for node_id in node_ids:
        first_task = assigned_jobs[node_id]
        # Check if no slot is assigned
        if not first_task:
            continue
        first_assigned_task = first_task[0]
        first_task_name = (
            f"vl_{first_assigned_task.job}_slot_{first_assigned_task.index}"
        )
        # print("first task:", first_task)
        # Add seperator line to describe which machine the tasks are assigned to
        plantuml_output += f"-- NAP {node_id} --\n"
        for assigned_slot_current in assigned_jobs[node_id]:
            slot_name = (
                f"vl_{assigned_slot_current.job}_slot_{assigned_slot_current.index}"
            )

            slot_start = assigned_slot_current.start
            slot_duration = assigned_slot_current.duration

            plantuml_output += f"[{slot_name}] requires {slot_duration} days\n"
            plantuml_output += f"note bottom\n  {slot_name}\nend note\n"
            plantuml_output += f"[{slot_name}] starts D+{slot_start}\n"
            plantuml_output += f"[{slot_name}] is colored in {color_to_job[assigned_slot_current.job]}\n"
            if slot_name != first_task_name:
                plantuml_output += (
                    f"[{slot_name}] displays on same row as [{first_task_name}]\n"
                )
            # Add slot to job dict
            job_to_slots_dict[assigned_slot_current.job].append(
                (
                    slot_start,
                    slot_name,
                    assigned_slot_current.end,
                    assigned_slot_current.duration,
                )
            )
    # Add connection arrows to output
    print(job_to_slots_dict)
    plantuml_output += "\n"
    for job in job_to_slots_dict:
        current_slots = job_to_slots_dict[job]
        current_slots.sort(key=lambda x: x[0])
        for slot in range(len(current_slots) - 1):
            # plantuml_output += f"[{current_slots[slot][1]}] -[{color_to_job[job]}]> [{current_slots[slot+1][1]}]\n"
            end_difference = (
                current_slots[slot + 1][2]
                - current_slots[slot][2]
                + current_slots[slot][3]
            )
            plantuml_output += (
                f"[{current_slots[slot + 1][1]}] starts {end_difference} days before "
                f"[{current_slots[slot][1]}]'s end with {color_to_job[job]} link\n"
            )

    # Add transparent slot to create cycle time if cycle time greater 0
    if cycle_time > 0:
        plantuml_output += "\n"
        plantuml_output += f"""[cycle_time] starts D+{int(cycle_time)}
[cycle_time] is colored in #00000000
[cycle_time] requires 1 day\n\n"""

    plantuml_output += "@endgantt"

    with open(
        os.path.join(output_directory_name, filename), "w", encoding="utf-8"
    ) as f:
        f.write(plantuml_output)
    # print(plantuml_output)


def export_dot(
    input_graph, filename="network_export.dot", output_directory_name="output"
):
    """
    :param input_graph: Networkx graph
    :param filename: Name of the DOT output file
    :param output_directory_name: Name of the output directory
    :return:
    """
    # Copy only needed information from input graph
    node_ids = nx.get_node_attributes(input_graph, "name")
    node_names = [node_ids[id] for id in node_ids.keys()]
    print("Export dot node names:", node_names)
    export_graph = input_graph.__class__()
    export_graph.add_nodes_from(input_graph.nodes)
    export_graph.add_edges_from(input_graph.edges)

    # Change name attribute
    if node_names:
        nx.set_node_attributes(export_graph, node_ids, "nap_name")

    # Remove multi edges
    export_graph_simple = nx.Graph(export_graph)

    # Write output DOT file
    nx.drawing.nx_pydot.write_dot(
        export_graph_simple, os.path.join(output_directory_name, filename)
    )


def print_schedule_in_graph(
    network,
    schedule_length,
    slots,
    logger=None,
    output_directory_name="output",
    output_filename="tdma_schedule_interactive.html",
):
    """
    Export interactive diagram of the schedule in the network

    :param network: Networkx graph
    :param schedule_length: Length of the schedule
    :param slots: Dict of interfaces with their assigned slots
    """
    log = logging.getLogger(logger)

    node_size = 50

    # Get used slots and interfaces
    used_slots = {a: b for a, b in slots.items() if b}
    interface_infos = {
        a: {}
        for a in [
            b
            for b, c in network.nodes(data=True)
            if c["function"] == "inner_domain_interface"
        ]
    }
    for a, b in used_slots.items():
        interface_infos[a]["slots"] = b

    interface_inner_ids = list(interface_infos.keys())
    # VLs
    vl_ids = sorted(list({b.job for a in used_slots.values() for b in a}))

    # Create node mass dict
    # mass_map = {"nap": 2, "outer_domain_interface": 0.5, "inner_domain_interface": 1}
    # node_mass = {n: mass_map[network.nodes[n]["function"]] for n in network.nodes()}

    # Get node positions from networkx layout
    # positions = nx.drawing.forceatlas2_layout(
    #     network, seed=42, node_mass=node_mass, weight="weight"
    # )
    # positions = nx.drawing.spring_layout(network, seed=42, weight="weight")
    # positions = nx.nx_agraph.graphviz_layout(network, prog="circo")
    positions = nx.kamada_kawai_layout(network, weight="weight", scale=25)

    # Node positions
    node_x, node_y = zip(*[positions[node] for node in network.nodes()])
    nodes_nap, node_nap_x, node_nap_y = zip(
        *[
            [node] + list(positions[node])
            for node in network.nodes()
            if network.nodes[node]["function"] == "nap"
        ]
    )
    nodes_outer_domain, node_outer_domain_x, node_outer_domain_y = zip(
        *[
            [node] + list(positions[node])
            for node in network.nodes()
            if network.nodes[node]["function"] == "outer_domain_interface"
        ]
    )
    (
        nodes_inner_domain_interface,
        node_inner_domain_interface_x,
        node_inner_domain_interface_y,
    ) = zip(
        *[
            [node] + list(positions[node])
            for node in network.nodes()
            if network.nodes[node]["function"] == "inner_domain_interface"
        ]
    )

    # Edge positions
    edge_x, edge_y = [], []
    for e in network.edges:
        x0, y0 = positions[e[0]]
        x1, y1 = positions[e[1]]
        # Create double edges for connections between two inner domain interfaces
        if network.edges[e[0], e[1], e[2]]["function"] == "inner_link":
            vektor = (x0 - x1, y0 - y1)
            log.debug(f"Vektor: {vektor}")
            vektor_90 = (vektor[1], -vektor[0])
            norm = (vektor_90[0] ** 2.0 + vektor_90[1] ** 2.0) ** 0.5
            log.debug(f"Norm: {norm}")
            vektor_90_normalized = (vektor_90[0] / norm, vektor_90[1] / norm)
            log.debug(f"normalized vektor: {vektor_90_normalized}")

            # Add start and end point of each linear edge
            interface_infos[e[0]]["edge_positions_x"] = [
                # x0,
                x0 + vektor_90_normalized[0],
                x1 + vektor_90_normalized[0],
                # x1,
                None,
            ]
            interface_infos[e[0]]["edge_positions_y"] = [
                # y0,
                y0 + vektor_90_normalized[1],
                y1 + vektor_90_normalized[1],
                # y1,
                None,
            ]
            interface_infos[e[1]]["edge_positions_x"] = [
                # x1,
                x1 - vektor_90_normalized[0],
                x0 - vektor_90_normalized[0],
                # x0,
                None,
            ]
            interface_infos[e[1]]["edge_positions_y"] = [
                # y1,
                y1 - vektor_90_normalized[1],
                y0 - vektor_90_normalized[1],
                # y0,
                None,
            ]
            # Add start and end point of each spline edge
            interface_infos[e[0]]["edge_positions_spline_x"] = [
                x0,
                (x0 + x1) / 2 + vektor_90_normalized[0],
                x1,
                None,
            ]
            interface_infos[e[0]]["edge_positions_spline_y"] = [
                y0,
                (y0 + y1) / 2 + vektor_90_normalized[1],
                y1,
                None,
            ]
            interface_infos[e[1]]["edge_positions_spline_x"] = [
                x1,
                (x1 + x0) / 2 - vektor_90_normalized[0],
                x0,
                None,
            ]
            interface_infos[e[1]]["edge_positions_spline_y"] = [
                y1,
                (y1 + y0) / 2 - vektor_90_normalized[1],
                y0,
                None,
            ]

            # Add annotation positions
            interface_infos[e[0]]["annotation_position_x"] = (
                x0 - vektor[0] / 2 + vektor_90_normalized[0] * 1.5
            )
            interface_infos[e[0]]["annotation_position_y"] = (
                y0 - vektor[1] / 2 + vektor_90_normalized[1] * 1.5
            )
            interface_infos[e[1]]["annotation_position_x"] = (
                x1 + vektor[0] / 2 - vektor_90_normalized[0] * 1.5
            )
            interface_infos[e[1]]["annotation_position_y"] = (
                y1 + vektor[1] / 2 - vektor_90_normalized[1] * 1.5
            )
        else:
            edge_x += [x0, x1, None]
            edge_y += [y0, y1, None]

    # Default network edge trace for edges that don't connect two inner domain interfaces
    edge_trace = go.Scatter(
        x=edge_x,
        y=edge_y,
        line={
            "width": 1.0,
            "color": "#888",
            "dash": "solid",
            "shape": "linear",
            "backoff": [node_size / 2] * 2,
        },
        hoverinfo="none",
        mode="lines",
        visible=True,
        showlegend=False,
    )

    # Edge traces and annotations for edges that connect two inner domain interfaces
    interface_inner_annotations = []
    # for interface, interface_item in interface_infos.items():
    for interface in interface_inner_ids:
        interface_item = interface_infos[interface]
        interface_trace = go.Scatter(
            x=interface_item["edge_positions_spline_x"],
            y=interface_item["edge_positions_spline_y"],
            line={
                "width": 1.0,
                "color": "#888",
                "dash": "solid",
                "shape": "spline",
                "smoothing": 0.5,
                # "backoff": 30,
            },
            hoverinfo="skip",
            mode="lines+markers",
            marker={
                "size": [0, 0, 20],
                "symbol": "arrow",
                "angleref": "previous",
                "standoff": node_size / 2,
                "line_width": 0.5,
                "opacity": 1.0,
            },
            visible=True,
            showlegend=False,
        )
        interface_item["trace"] = interface_trace

        # Add annotation at center of each line
        interface_inner_annotations.append(
            {
                "showarrow": False,
                "x": interface_item["annotation_position_x"],
                "y": interface_item["annotation_position_y"],
                # "text": interface,
                "text": "",
                "font": {
                    "color": "#ffffff",
                },
            }
        )
    edge_trace_inner = [interface_infos[a]["trace"] for a in interface_inner_ids]

    # Node default dict
    node_dict_default = {
        "x": node_x,
        "y": node_y,
        "mode": "markers+text",
        "hoverinfo": "text",
        "text": [f"{a}" for a in network.nodes()],
        "legendgroup": "NAPs and Interfaces",
        "legendgrouptitle_text": "NAPs and Interfaces",
        # "legend": "legend",
        # textposition='inside',
        "marker": {
            "size": node_size,
            "line_width": 1,
        },
    }

    # NAP markers
    node_nap_trace = go.Scatter(
        arg=node_dict_default
        | {
            "x": node_nap_x,
            "y": node_nap_y,
            "text": [f"{n}" for n in nodes_nap],
            "name": "NAPs",
            "marker_symbol": "hexagon",
        },
    )

    # Outer domain nodes markers
    node_outer_domain_trace = go.Scatter(
        arg=node_dict_default
        | {
            "x": node_outer_domain_x,
            "y": node_outer_domain_y,
            "text": [f"{n[1]}" for n in nodes_outer_domain],
            "name": "Outer Domain Interfaces",
            "marker_symbol": "square",
        }
    )

    # Inner domain interface markers
    node_inner_domain_interface_trace = go.Scatter(
        arg=node_dict_default
        | {
            "x": node_inner_domain_interface_x,
            "y": node_inner_domain_interface_y,
            "text": [f"{n}" for n in nodes_inner_domain_interface],
            "name": "Inner Domain Interfaces",
            "marker_symbol": "circle",
        }
    )

    # Select colors associated with VLs
    # vl_color_palette = px.colors.qualitative.Light24
    vl_color_palette = cc.b_glasbey_bw_minc_20_maxl_70
    vl_id_to_color = {
        v: vl_color_palette[i % len(vl_color_palette)] for i, v in enumerate(vl_ids)
    }

    # Nonvisible traces to add VLs to legend
    vl_legend_scatter = []
    for vl_id in vl_ids:
        vl_legend_scatter.append(
            go.Scatter(
                x=[None, None],
                y=[None, None],
                mode="lines",
                legendgroup="Virtual Links",
                legendgrouptitle_text="Virtual Links",
                # legend="legend",
                name=vl_id,
                showlegend=True,
                visible=True,
                line_color=vl_id_to_color[vl_id],
            )
        )

    fig = go.Figure(
        data=edge_trace_inner
        + vl_legend_scatter
        + [
            edge_trace,
            node_nap_trace,
            node_outer_domain_trace,
            node_inner_domain_interface_trace,
        ],
        layout=go.Layout(
            title_text="TDMA Scheduler",
            showlegend=True,
            # hovermode='closest',
            # margin=dict(b=20, l=5, r=5, t=40),
            # legend={"title_text": "Virtual Links", "y": 1.0},
            legend_groupclick="toggleitem",
            legend_itemdoubleclick="toggleothers",
            xaxis={"showgrid": False, "zeroline": False, "showticklabels": False},
            yaxis={"showgrid": False, "zeroline": False, "showticklabels": False},
            annotations=interface_inner_annotations,
        ),
    )

    # Get start and end times of each slot
    slot_start_end_times = [int(schedule_length)]
    for interface, assigned_slots in used_slots.items():
        for slot in assigned_slots:
            slot_start_end_times += [slot.start, slot.start + slot.duration]
    slot_start_end_times_set = sorted(list(set(slot_start_end_times)))

    time_steps = []
    for time_index, time in enumerate(slot_start_end_times_set):
        colors = ["#888"] * len(edge_trace_inner)
        hover_text = [""] * len(edge_trace_inner)
        current_annotation = copy.deepcopy(interface_inner_annotations)
        # Check for each interface if it is used at the current time step
        for interface, assigned_slots in used_slots.items():
            for slot in assigned_slots:
                if slot.start <= time < slot.start + slot.duration:
                    vl_color = vl_id_to_color[slot.job]
                    interface_index = interface_inner_ids.index(interface)
                    colors[interface_index] = vl_color
                    hover_text[interface_index] = str(slot.job)
                    # Change annotation text
                    current_annotation[interface_index]["text"] = "VL" + str(slot.job)
                    # Add border to annotation
                    current_annotation[interface_index] |= {
                        "bordercolor": vl_color,
                        "borderwidth": 2,
                        "borderpad": 2,
                        "bgcolor": vl_color,
                        "opacity": 0.9,
                    }
        step = {
            "label": (
                f"{time} to {slot_start_end_times_set[time_index + 1] - 1}"
                if time_index < len(slot_start_end_times_set) - 1
                and time < slot_start_end_times_set[time_index + 1] - 1
                else str(time)
            ),
            "method": "update",
            "args": [
                {
                    "line.color": colors
                    + [
                        c.line.color
                        for c in vl_legend_scatter
                        + [
                            edge_trace,
                            node_nap_trace,
                            node_outer_domain_trace,
                            node_inner_domain_interface_trace,
                        ]
                    ],
                    "hovertext": hover_text
                    + [None] * (len(fig.data) - len(edge_trace_inner)),
                },
                {"annotations": current_annotation},
            ],
        }
        time_steps.append(step)

    sliders = [
        {"active": 0, "currentvalue": {"prefix": "Timestep: "}, "steps": time_steps}
    ]

    fig.update_layout(sliders=sliders)

    # Show figure
    # fig.show()

    # Export figure to HTML
    fig.write_html(os.path.join(output_directory_name, output_filename),
        config={"doubleClickDelay": 600})


def plotly_gantt(
    slots,
    schedule_length,
    logger=None,
    output_directory_name="output",
    output_filename="tdma_gantt_interactive.html",
):
    """
    Export interactive gantt diagram

    :param slots: Dict of interfaces with their assigned slots
    :param schedule_length: Length of the schedule
    """

    log = logging.getLogger(logger)
    log.info("Start generating interactive gantt diagram")

    # Get used slots and interfaces
    slots_used = {a: b for a, b in slots.items() if b}
    interface_infos = {a: {"slots": b} for a, b in slots_used.items()}
    interface_inner_ids = sorted(list(interface_infos.keys()))
    # VLs
    vl_ids = sorted(list({b.job for a in slots_used.values() for b in a}))

    # VL color palette
    vl_color_palette = cc.b_glasbey_bw_minc_20_maxl_70
    vl_id_to_color = {
        str(v): vl_color_palette[i % len(vl_color_palette)]
        for i, v in enumerate(vl_ids)
    }

    # Set start date for diagram to unix epoch 0
    start_date = datetime.datetime.fromtimestamp(0, datetime.UTC)

    df = pd.DataFrame(
        [
            {
                "Task": interface,
                "Start": slot.start,
                "Start_time": start_date + datetime.timedelta(seconds=slot.start),
                "Finish": slot.start + slot.duration,
                "Finish_time": start_date
                + datetime.timedelta(seconds=slot.start + slot.duration),
                "Resource": str(slot.job),
            }
            for interface, assigned_slots in slots_used.items()
            for slot in assigned_slots
        ]
    )

    # Export figure using old plotly figure factory
    fig_ff = ff.create_gantt(
        df,
        title="TDMA Gantt Diagram",
        index_col="Resource",
        bar_width=0.4,
        show_colorbar=True,
        colors=vl_color_palette,
        group_tasks=True,
    )
    fig_ff.update_layout(xaxis_type="linear", autosize=True)

    # Show figure
    # fig_ff.show()

    # Export figure to HTML
    fig_ff.write_html(
        os.path.join(
            output_directory_name, output_filename.replace(".html", "") + "_ff.html"
        ),
        config={"doubleClickDelay": 600},
    )

    fig_px = px.timeline(
        df,
        title="TDMA Gantt Diagram",
        x_start="Start_time",
        x_end="Finish_time",
        y="Task",
        color="Resource",
        color_discrete_map=vl_id_to_color,
        text="Resource",
        labels={
            "Resource": "VLs",
            "Task": "Interface",
        },
        category_orders={
            "Resource": [str(v) for v in vl_ids],
            "Task": interface_inner_ids,
        },
        # Add custom data for hover labels
        custom_data=["Start", "Finish"],
    )
    fig_px.update_layout(
        xaxis={
            # Set tick format to seconds since unix epoch start
            "tickformat": "%s",
            "title": "Time Units",
        },
        uniformtext_minsize=14,
        uniformtext_mode="hide",
    )
    fig_px.update_traces(textposition="inside")
    fig_px.update_traces(
        hovertemplate="VL: %{text}<br>Start: %{customdata[0]}<br>Finish: %{customdata[1]}<extra></extra>"
    )

    # Add vertical line for schedule end time
    # Bug in plotly prevents direct use of datetime, so conversion to milliseconds since epoch is necessary
    # See: https://github.com/plotly/plotly.py/issues/3065
    schedule_length_date = int(
        (
            start_date
            + datetime.timedelta(seconds=schedule_length)
            - datetime.timedelta(hours=1)
        ).timestamp()
        * 1000
    )
    fig_px.add_vline(
        x=schedule_length_date,
        line_dash="dot",
        line_width=1,
        annotation_text=f"Schedule ends<br>at {int(schedule_length)}",
        annotation_position="top",
        annotation_yshift=0,
    )

    # fig_px.show()
    fig_px.write_html(os.path.join(output_directory_name, output_filename))


# def main():
#     # Define command line arguments
#     parser = argparse.ArgumentParser(
#         prog="visualizer",
#         description="Visualizer for TDMA",
#         formatter_class=argparse.ArgumentDefaultsHelpFormatter,
#     )
#     parser.add_argument(
#         "input-scheduler",
#         help="scheduler input file name",
#         nargs="?",
#         default="example_network.json",
#     )
#     parser.add_argument(
#         "-o",
#         "--output-folder",
#         help="output folder name",
#         default="output",
#         required=False,
#     )
#     parser.add_argument(
#         "-l",
#         "--log-level",
#         help="log level",
#         choices=["debug", "info", "warning", "warn", "error", "fatal", "critical"],
#         default="info",
#         required=False,
#     )
#     # parser.print_help()
#
#     # Read command line inputs
#     args = vars(parser.parse_args())
#     # print("args:", args)
#     input_file_name = args["input-scheduler"]
#     output_folder_name = args["output_folder"]
#     log_level = args["log_level"]
#
#     script_dir = os.path.dirname(__file__)
#     output_folder_path = os.path.join(script_dir, output_folder_name)
#
#
# if __name__ == "__main__":
#     main()
