#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
A QGIS plugin for writing input files to the Conefor software.
'''

import os

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *

from conefordialog import ConeforDialog


#TODO
# Add a label with progress info to the GUI
# Write the logic for the area and distance queries
#   Calculate area and distances with QgsdistanceArea
# Hook up the progress bar, possibly by emitting signals
# Filter the id_attribute field choices to show only unique fields
# create a Makefile
# Write the help dialog
# Provide better docstrings
# Add more testing layers (empty features, empty fields)

class NoFeaturesToProcessError(Exception):
    pass


class ConeforProcessor(object):

    def __init__(self, iface):
        self.iface = iface
        self.registry = QgsMapLayerRegistry.instance()

    def initGui(self):
        self.action = QAction(QIcon(':plugins/conefor_dev/icon.png'), 
                              'Conefor inputs plugin. Requires at least one ' \
                              'loaded vector layer.', self.iface.mainWindow())
        #self.action.setWhatsThis('')
        self.action.setStatusTip('Conefor inputs plugin (requires at least ' \
                                 'one loaded vector layer)')
        QObject.connect(self.action, SIGNAL('triggered()'), self.run)
        QObject.connect(self.registry,
                        SIGNAL('layersAdded(QList<QgsMapLayer*>)'),
                        self.toggle_availability)
        QObject.connect(self.registry,
                        SIGNAL('layersWillBeRemoved(QStringList)'),
                        self.toggle_availability)
        self.iface.addPluginToVectorMenu('&Conefor inputs', self.action)
        self.iface.addVectorToolBarIcon(self.action)

    def unload(self):
        self.iface.removePluginVectorMenu('&Conefor inputs', self.action)
        self.iface.removeVectorToolBarIcon(self.action)

    def run(self):
        usable_layers = self.get_usable_layers()
        cl = self.iface.mapCanvas().currentLayer()
        if cl not in usable_layers.values():
            cl = usable_layers.values()[0]
        dialog = ConeforDialog(usable_layers, cl, self)
        result = dialog.exec_()

    def toggle_availability(self, the_layers):
        '''
        Toggle the plugin's availability.

        inputs:

            the_layers - can be either a QStringList or a Qlist of
                QgsVectorLayers depending on wether the method is called
                by the 'layersWillBeRemoved' or the 'layersAdded' signals
                of the mapLayerRegistry.

        This method is called whenever the mapLayerRegistry emits either
        the 'layersAdded' or the 'layersWillBeRemoved' signals.

        Plugin availability depends on the availability of vector
        layers loaded in QGIS.
        '''

        usable_layers = self.get_usable_layers()
        # mapLayerRegistry's layersWillBeRemoved signal is sent before the
        # layers are removed so we need to check which layers are going to be
        # removed and act as if they were already gone
        if type(the_layers) == QStringList:
            for to_delete in the_layers:
                if usable_layers.get(QString(to_delete)) is not None:
                    del usable_layers[QString(to_delete)]
        one_vector_loaded = False
        if any(usable_layers):
            for layer_id, layer in usable_layers.iteritems():
                if layer.type() == QgsMapLayer.VectorLayer:
                    one_vector_loaded = True
                    break
        self.action.setEnabled(one_vector_loaded)

    def get_usable_layers(self):
        '''
        return a dictionary with layerid as key and layer as value.

        This plugin only works with vector layers of types Point, MultiPoint,
        Polygon, MutiPolygon.
        '''

        usable_layers = dict()
        loaded_layers = self.registry.mapLayers()
        for layer_id, the_layer in loaded_layers.iteritems():
            if the_layer.type() == QgsMapLayer.VectorLayer:
                if the_layer.geometryType() in (QGis.Point, QGis.Polygon):
                    usable_layers[layer_id] = the_layer
        return usable_layers

    def run_queries(self, layers, output_dir, create_distance_files):
        '''
        Create the Conefor inputs files.

        Inputs:

            layers - A list of dictionaries that have the parameters of the
                layers to process. Each dictionary has the following key/value
                pairs:

                    - layer : a QgsMapLayer to be processed
                    - id_attribute : the name of the attribute to be used as
                      an id for Conefor queries
                    - edge_distance : a boolean indicating if the edge
                      distance query is to be performed on this layer
                    - centroid_distance : a boolean indicating if the
                      centroid distance query is to be performed on this
                      layer
                    - area : a boolean indicating if the area query is to 
                      be performed on this layer
                    - attribute : the name of the attribute to use for the
                      attribute query. Can be None, resulting in no
                      attribute query being performed

            output_dir - The full path to the desired output directory;

            create_distance_files - A boolean indicating if the vector files
                with the lines representing the distances should be created;
        '''

        for index, layer_parameters in enumerate(layers):
            try:
                self.process_layer(layer_parameters['layer'],
                                   layer_parameters['id_attribute'],
                                   layer_parameters['area'],
                                   layer_parameters['attribute'],
                                   layer_parameters['centroid_distance'],
                                   layer_parameters['edge_distance'],
                                   output_dir)
            except NoFeaturesToProcessError:
                print('Layer %s has no features to process' % \
                      layer_parameters['layer'].name())

    def _write_file(self, data, output_dir, output_name):
        '''
        Write a text file with the input data.
        '''

        print('_write_file called')
        output_path = os.path.join(output_dir, output_name)
        with open(output_path, 'w') as file_handler:
            for line in data:
                file_handler.write(line)

    def _write_distance_file(layer_parameters, distances):

        raise NotImplementedError

    def process_layer(self, layer, id_attribute, area, attribute,
                      centroid, edge, output_dir):
        '''
        Process an individual layer.

        Inputs:

            layer - A QgsVector layer

            id_attribute - The name of the attribute to be used as id

            area - A boolean indicating if the area is to be processed

            attribute - The name of the attribute to be processed. If None,
                the attribute process does not take place

            centroid - A boolean indicating if the centroid distances are to
                be calculated

            edge - A boolean indicating if the edge distances are to
                be calculated

            output_dir - The directory where the output files are to be saved
        '''

        files_progress = 10.0
        file_write_step = files_progress / self._determine_num_files(area,
                                                                     attribute,
                                                                     centroid,
                                                                     edge)
        num_features = layer.featureCount()
        feat_steps = 0
        if (attribute is not None) or area:
            feat_steps += num_features
        if feat_steps == 0:
            raise NoFeaturesToProcessError
        progress_step = (100.0 - files_progress) / feat_steps
        attribute_data = []
        area_data = []
        centroid_data = []
        edge_data = []
        feat = QgsFeature()
        feat_iterator = layer.getFeatures()
        progress = 0
        while feat_iterator.nextFeature(feat):
            id_attr = feat.attribute(id_attribute).toString()
            if attribute is not None:
                attr = feat.attribute(attribute).toString()
                attribute_data.append('%s\t%s\n' % (id_attr, attr))
            if area:
                area = feat.geometry().area()
                area_data.append('%s\t%s\n' % (id_attr, area))
            progress += progress_step
        if any(area_data):
            output_name = 'nodes_calculated_area_%s' % layer.name()
            self._write_file(area_data, output_dir, output_name)
            progress += file_write_step
        if any(attribute_data):
            output_name = 'nodes_%s_%s' % (attribute, layer.name())
            self._write_file(attribute_data, output_dir, output_name)
            progress += file_write_step
        if any(centroid_data):
            output_name = 'distances_centroids_%s' % layer.name()
            self._write_file(centroid_data, output_dir, output_name)
            progress += file_write_step
        if any(edge_data):
            output_name = 'distances_edges_%s' % layer.name()
            self._write_file(attribute_data, output_dir, output_name)
            progress += file_write_step
        return progress

    def _determine_num_files(self, area, attribute, centroid, edge):
        files_to_write = 0
        if area:
            files_to_write += 1
        if attribute is not None:
            files_to_write += 1
        if centroid:
            files_to_write += 1
        if edge:
            files_to_write += 1
        return files_to_write