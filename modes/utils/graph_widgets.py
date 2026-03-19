"""
Graph Widgets Module
Handles creation and management of all graphs for acquisition mode

Doc status: done, MK, 01/30/2026
"""
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt
import pyqtgraph as pg
from datetime import datetime

try:
    from modes.utils.config import MAX_DUT_UNITS
except ImportError:
    MAX_DUT_UNITS = 8


class TimeAxisItem(pg.AxisItem):
    """Custom axis item to display Unix timestamps as HH:MM:SS"""
    def __init__(self, *args, **kwargs):
        """
        Initialize the custom time axis item.
        
        Creates a PyQtGraph axis that displays Unix timestamps as formatted
        time strings (HH:MM:SS).
        
        Args:
            *args: Variable positional arguments passed to parent AxisItem.
            **kwargs: Variable keyword arguments passed to parent AxisItem.
        """
        super().__init__(*args, **kwargs)
        
    def tickStrings(self, values, scale, spacing):
        """Override to format timestamps as HH:MM:SS"""
        strings = []
        for v in values:
            try:
                dt = datetime.fromtimestamp(v)
                strings.append(dt.strftime('%H:%M:%S\n%m/%d'))
            except:
                strings.append('')
        return strings


class GraphManager:
    """Manages all graph widgets and plotting"""
    
    def __init__(self):
        """
        Initialize the graph manager.
        
        Sets up color schemes and creates real-time graph widgets for displaying
        DUT sensor data and IBP reference measurements including conductivity and
        temperature.
        """
        self.max_dut_units = max(1, int(MAX_DUT_UNITS))

        # Colors for DUT units (extended to support 8+ channels deterministically).
        palette = [
            "#BB4848",  # Red
            "#379137",  # Green
            "#5151A7",  # Blue
            "#96963C",  # Yellow
            "#913D91",  # Magenta
            "#A9C0C0",  # White-ish cyan
            "#FF8C00",  # Orange
            "#00CED1",  # Dark turquoise (unit 8)
        ]
        self.unit_colors = {
            unit_id: palette[(unit_id - 1) % len(palette)]
            for unit_id in range(1, self.max_dut_units + 1)
        }
        
        # Colors for reference devices
        self.reference_colors = {
            1: "#FF6B35",  # Orange
            2: "#00D9FF",  # Cyan
        }
        
        # Plot references
        self.settling_plots = {}
        self.measurement_plots = {}
        self.ref_settling_plots = {}
        self.ref_measurement_plots = {}
        
        # Graph widgets
        self.settling_graph = None
        self.measurement_graph = None
        self.ref_settling_graph = None
        self.ref_measurement_graph = None
    
    def create_graphs_layout(self):
        """Create the complete graphs layout with 4 graphs in 2x2 grid"""
        graphs_container = QVBoxLayout()
        
        # Top row of graphs
        top_graphs = QHBoxLayout()
        top_graphs.addLayout(self._create_dut_conductivity_graph())
        top_graphs.addLayout(self._create_ref_conductivity_graph())
        graphs_container.addLayout(top_graphs)
        
        # Bottom row of graphs
        bottom_graphs = QHBoxLayout()
        bottom_graphs.addLayout(self._create_dut_rtd_graph())
        bottom_graphs.addLayout(self._create_ref_rtd_graph())
        graphs_container.addLayout(bottom_graphs)
        
        return graphs_container
    
    def _create_dut_conductivity_graph(self):
        """Create DUT conductivity graph (top left)"""
        layout = QVBoxLayout()
        
        label = QLabel("DUT_conductivity")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("""
            QLabel {
                color: white;
                font-weight: bold;
                font-size: 12pt;
                padding: 3px;
            }
        """)
        layout.addWidget(label)
        
        time_axis = TimeAxisItem(orientation='bottom')
        self.settling_graph = pg.PlotWidget(axisItems={'bottom': time_axis})
        self.settling_graph.setBackground('k')
        self.settling_graph.setLabel('left', 'Resistance (Ohm)')
        self.settling_graph.setLabel('bottom', 'Time')
        self.settling_graph.showGrid(x=True, y=True, alpha=0.3)
        self.settling_graph.addLegend()
        time_axis.enableAutoSIPrefix(False)
        
        # Create plot lines for each DUT unit
        for unit_id in range(1, self.max_dut_units + 1):
            plot = self.settling_graph.plot(
                pen=pg.mkPen(self.unit_colors[unit_id], width=2),
                name=f'J{unit_id}'
            )
            self.settling_plots[unit_id] = plot
        
        layout.addWidget(self.settling_graph)
        return layout
    
    def _create_dut_rtd_graph(self):
        """Create DUT RTD graph (bottom left)"""
        layout = QVBoxLayout()
        
        label = QLabel("DUT_RTD")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("""
            QLabel {
                color: white;
                font-weight: bold;
                font-size: 12pt;
                padding: 3px;
            }
        """)
        layout.addWidget(label)
        
        time_axis = TimeAxisItem(orientation='bottom')
        self.measurement_graph = pg.PlotWidget(axisItems={'bottom': time_axis})
        self.measurement_graph.setBackground('k')
        self.measurement_graph.setLabel('left', 'Resistance (Ohm)')
        self.measurement_graph.setLabel('bottom', 'Time')
        self.measurement_graph.showGrid(x=True, y=True, alpha=0.3)
        self.measurement_graph.addLegend()
        time_axis.enableAutoSIPrefix(False)
        
        # Create plot lines for each DUT unit
        for unit_id in range(1, self.max_dut_units + 1):
            plot = self.measurement_graph.plot(
                pen=pg.mkPen(self.unit_colors[unit_id], width=2),
                name=f'J{unit_id}'
            )
            self.measurement_plots[unit_id] = plot
        
        layout.addWidget(self.measurement_graph)
        return layout
    
    def _create_ref_conductivity_graph(self):
        """Create Reference conductivity graph (top right)"""
        layout = QVBoxLayout()
        
        label = QLabel("Reference_conductivity")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("""
            QLabel {
                color: white;
                font-weight: bold;
                font-size: 12pt;
                padding: 3px;
            }
        """)
        layout.addWidget(label)
        
        time_axis = TimeAxisItem(orientation='bottom')
        self.ref_settling_graph = pg.PlotWidget(axisItems={'bottom': time_axis})
        self.ref_settling_graph.setBackground('k')
        self.ref_settling_graph.setLabel('left', 'IBP Conductivity (mS/cm)')
        self.ref_settling_graph.setLabel('bottom', 'Time')
        self.ref_settling_graph.showGrid(x=True, y=True, alpha=0.3)
        self.ref_settling_graph.addLegend()
        time_axis.enableAutoSIPrefix(False)
        
        # Create plot lines for reference devices
        for ref_id in range(1, 3):
            plot = self.ref_settling_graph.plot(
                pen=pg.mkPen(self.reference_colors[ref_id], width=2),
                name=f'Ref{ref_id}'
            )
            self.ref_settling_plots[ref_id] = plot
        
        layout.addWidget(self.ref_settling_graph)
        return layout
    
    def _create_ref_rtd_graph(self):
        """Create Reference RTD graph (bottom right)"""
        layout = QVBoxLayout()
        
        label = QLabel("Reference_RTD")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("""
            QLabel {
                color: white;
                font-weight: bold;
                font-size: 12pt;
                padding: 3px;
            }
        """)
        layout.addWidget(label)
        
        time_axis = TimeAxisItem(orientation='bottom')
        self.ref_measurement_graph = pg.PlotWidget(axisItems={'bottom': time_axis})
        self.ref_measurement_graph.setBackground('k')
        self.ref_measurement_graph.setLabel('left', 'IBP Temperature (°C)')
        self.ref_measurement_graph.setLabel('bottom', 'Time')
        self.ref_measurement_graph.showGrid(x=True, y=True, alpha=0.3)
        self.ref_measurement_graph.addLegend()
        time_axis.enableAutoSIPrefix(False)
        
        # Create plot lines for reference devices
        for ref_id in range(1, 3):
            plot = self.ref_measurement_graph.plot(
                pen=pg.mkPen(self.reference_colors[ref_id], width=2),
                name=f'Ref{ref_id}'
            )
            self.ref_measurement_plots[ref_id] = plot
        
        layout.addWidget(self.ref_measurement_graph)
        return layout
    
    def update_dut_plots(self, unit_id, timestamps, settling_data, measurement_data):
        """Update DUT plots for a specific unit"""
        if 1 <= unit_id <= self.max_dut_units:
            self.settling_plots[unit_id].setData(timestamps, settling_data)
            self.measurement_plots[unit_id].setData(timestamps, measurement_data)
    
    def update_reference_plots(self, ref_id, timestamps, settling_data, measurement_data):
        """Update reference device plots"""
        if 1 <= ref_id <= 2:
            self.ref_settling_plots[ref_id].setData(timestamps, settling_data)
            self.ref_measurement_plots[ref_id].setData(timestamps, measurement_data)
    
    def clear_all_plots(self):
        """Clear all plot data"""
        for unit_id in range(1, self.max_dut_units + 1):
            self.settling_plots[unit_id].setData([], [])
            self.measurement_plots[unit_id].setData([], [])
        
        for ref_id in range(1, 3):
            self.ref_settling_plots[ref_id].setData([], [])
            self.ref_measurement_plots[ref_id].setData([], [])
