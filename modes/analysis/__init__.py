"""
Analysis module for alyPyAcquisition
Contains conductivity sensor calibration analysis tools
Optimized for Dual-Range Aly Model 2 only
"""

from .conductivity_analysis_lib import (
    read_conductivity_data,
    plot_experiment,
    gen_fit_array_from_plateaus,
    temperature_fit,
    fit_dual_range_aly_model_2,
    predict_linear
)

__all__ = [
    'read_conductivity_data',
    'plot_experiment',
    'gen_fit_array_from_plateaus',
    'temperature_fit',
    'fit_dual_range_aly_model_2',
    'predict_linear'
]
