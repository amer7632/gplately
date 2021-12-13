""" A module that utilises Pooch functionalities for accessing web-based data on-the-fly from GPlately's Data Server. 

GPlately's server is a Python dictionary whose keys are collection label strings (i.e. "Muller2019", "Seton2012") 
that each correspond to download links of files from that collection. These links are taken from EarthByte's webDAV server.
Pooch is a data manager that downloads these files only when necessary and stores them in a machine's local cache. Once
a file has been downloaded once (and if it's a zip folder, if it's been unzipped once), Pooch will not redownload it - 
it will just re-access it from the cache.

Methods in this module provide all necessary files for GPlately's PlateReconstruction, Raster and PlotTopologies objects.
The 'DataServer' object accepts a user-input string specifying the data collection to extract from (i.e. "Muller2019").
It searches the GPlately data server for this string.

Classes
-------
DataServer
    A class to access GPlately's data server. Its only attribute is a string specifying the data collection to extract 
    from (i.e. "Muller2019"). It searches the GPlately DataServer for this string and downloads rotation models, 
    topology features, static polygons, netCDF4 rasters and polygon/polyline geometries from it.

Methods
-------
get_plate_reconstruction_files
    Extracts a rotation model, topology feature collection and some static polygons from the specified collection - these
    are the three parameters needed for GPlately's PlateReconstruction object.
get_topology_geometries
    Extracts a set of coastline, continent and COB geometries from the specified collection - these are the three parameters
    needed for GPlately's PlotTopologies object.
get_netcdf_rasters
    Extracts netCDF rasters from the specified collection - these are parameters for GPlately's Raster object.

Other auxiliary methods include:
fetch_from_zip(zip_url, file_ext=None, substring=None)
    Identifies and downloads a specific file from a zip file download URL using a file extension and a filename substring.
fetch_from_single_file(file_url, file_ext=None, substring=None)
    Identifies and downloads a specific file from a single file download URL using a file extension and a filename substring.
ignore_macOSX(filenames)
    Omits any files extracted from a MacOSX folder (for Mac users only).
remove_hash(filenames):
    Removes hashes used to identify web-based data on local caches from a filename path.
order_filenames_by_time(list_of_filenames):
    Orders a list of full file paths (typically rasters or other topology features) from recent to deep geological time. 
 
Sources
-------
Methods in this module take inspiration from and utilise:
Pooch : https://github.com/fatiando/pooch, DOI: https://doi.org/10.21105/joss.01943)
GPlatesReconstruction Model : S. Williams (2021) https://github.com/siwill22/GPlatesReconstructionModel/blob/dc29746d073050987fc91258b7786f1074df8efa/gprm/datasets/
Reconstructions.py#L174
"""
import pooch
from pooch import os_cache as _os_cache
from pooch import retrieve as _retrieve
from pooch import HTTPDownloader as _HTTPDownloader
from pooch import Unzip as _Unzip
import glob, os
import pygplates
import re
import numpy as np

def ignore_macOSX(filenames):
    """For Mac users: filters out duplicate filenames extracted from the __MACOSX folder.

    Parameters
    ----------
    filenames : list
        A list of full file paths that may include filenames in the __MACOSX directory.

    Returns
    -------
    filenames : list
        A list of full file paths ignoring filenames from the __MAC0SX directory.
    """
    fnames = filenames
    for fname in fnames:
        if fname.find("__MACOSX") != -1:
            fnames.remove(fname)
    if len(fnames) < len(filenames):
        print("There are no __MaCOSX files in this list.")
    return fnames


def remove_hash(filename):
    """Removes the identification hash ascribed to a cached file path. Useful for renaming directories.

    Attributes
    ----------
    filename : str
        A single string path to a cached file.

    Returns
    -------
    new_path : str
        The provided string path without its ID hash.
    """
    split_paths = filename.split("-")
    cache_path = split_paths[0][:-32]
    new_path = cache_path + "-".join(split_paths[1:])
    return new_path


def order_filenames_by_time(list_of_filenames):
    """Orders cached files in the same directory from recent to deep geological time (Ma) and stores files in an ordered 
    list (by default files labelled by time are not processed in time order). Useful for accessing netcdf4 raster data.

    Attributes
    ----------
    list_of_filenames : list of str
        A list of full paths to time-labelled files (e.g. continental_grid_0_Ma.nc). Should all have the same parent
        directory.

    Returns
    -------
    filenames_sorted : list of str
        The same list of provided paths, but ordered from present day (0 Ma) into deep geological time.

    """
    filenames_unsorted_indices = []
    # To sort by time, all digits in the file paths are identified. Hashes of file paths are removed for easy identification. 
    for i, file in enumerate(list_of_filenames):
        file = [int(str(element)) for element in re.split('([0-9]+)', remove_hash(file)) if element.isdigit()]
        filenames_unsorted_indices.append(file)

    # Digits that are common to all full file paths are ignored, leaving behind the files' geological time label.
    filenames_t = np.array(filenames_unsorted_indices).T
    filenames_t = [arr for arr in filenames_t if not all(element == arr[0] for element in arr)]

    # Remember the indices of the original list order, sort times in increasing order and sort the files in this order.
    sorted_filenames = sorted(enumerate(filenames_t[0]), key=lambda x: x[1])
    sorted_filename_indices = [file[0] for file in sorted_filenames]
    filenames_sorted = [list_of_filenames[index] for index in sorted_filename_indices]
    return filenames_sorted


def fetch_from_zip(zip_url, file_ext=None, substring=None, order_by_time=False):
    """Uses Pooch to download a file from a zip folder. Its filename must contain a specific substring and end
    with a specific file extension. Stores in local cache.
    
    For example, this can be used to extract rotation files by just specifying file_ext=".rot" and leaving 
    substring=None. Moreover, this can be used to extract COBs by specifying substring="cob" and file_ext=
    ".gpml" or ".shp". Note: if ever ".gpml" is passed as the desired file extension and nothing is found
    in the GPlately DataServer, this module will attempt to search for ".shp" file equivalents (and their
    counterpart extensions i.e. .xml) instead.
    
    Parameters
    ----------
    zip_url : str
        The full link to a zip folder's download URL.
    file_ext : str
        The file extension to extract (i.e. ".rot" for rotation files)
    substring : str
        A certain filename substring to look for (i.e "static" for static polygons)
    order_by_time : bool, default False
        Choose whether to order cached filenames by natsort order. Useful for filenames labelled by geological
        time, i.e. agegrids.
        
    Returns
    -------
    feature_filenames : str
        The full path to a set of files that have the specified file extension and/or a substring in its
        filename stored in a cache.
    """
    # Use pooch to download and unzip zip folder into local cache (Only executes once the first time)
    fnames = _retrieve(
        url=zip_url,
        known_hash=None,  
        downloader=_HTTPDownloader(progressbar=True),
        path=_os_cache('gplately'),
        processor=_Unzip(),
    )        
    dirname = os.path.split(fnames[0])[0]
    feature_filenames = []
    for subdir, dirs, files in os.walk(dirname):
        for file in files:
            if file_ext is not None:
                if file.endswith(file_ext):
                    if substring is not None:
                        if file.lower().find(substring) != -1:
                            feature_filenames.append(subdir+"/"+file)
                    else:
                        feature_filenames.append(subdir+"/"+file)                
            else:
                if substring is not None:
                    if file.lower().find(substring) != -1:
                        feature_filenames.append(subdir+"/"+file)
                else:
                    raise ValueError("Please supply a file extension and/or substring to extract.")
                            
    # If the user wants to extract .gpml file(s) from this zip file and none were found, try to look for a .shp
    # equivalent instead. 
    if file_ext == ".gpml" and len(feature_filenames) == 0: 
        if substring is not None:
            print(".gpml %s files were not found. Attempting to find .shp versions instead..." % (substring))
        else:
            print(".gpml files not found. Attempting to find .shp instead...")
        for subdir, dirs, files in os.walk(dirname):
            for file in files:
                if file.endswith(".shp"):
                    if substring is not None:
                        if file.lower().find(substring) != -1:
                            feature_filenames.append(subdir+"/"+file) 
                            print("Found a %s file with a .shp extension." %(substring))
                    else:
                        feature_filenames.append(subdir+"/"+file)
                        print("Found a file with a .shp extension." %(substring))   

    if len(feature_filenames) == 0:
        if substring is not None:
            print("Could not find %s files in this file collection." %(substring)) 
        else:
            print("Could not find files in this file collection.")

    feature_filenames = ignore_macOSX(feature_filenames)

    if order_by_time is True:
        feature_filenames = order_filenames_by_time(feature_filenames)
        return feature_filenames
    else:
        return feature_filenames
        

def fetch_from_single_link(file_url, file_ext=None, substring=None):
    """Uses Pooch to download a single file whose filename contains a specific substring and ends with a specific file extension.
    Stores downloaded file in local cache.

    Parameters
    ----------
    file_url : str
        The full link to a file's download URL.
    file_ext : str
        The file extension to extract (i.e. ".rot" for rotation files)
    substring : str
        A certain filename substring to look for (i.e "static" for static polygons)
        
    Returns
    -------
    feature_filenames : str
        The full path to the downloaded file.

    """
    # Use pooch to download topologies into local cache
    fname = _retrieve(
        url=file_url,
        known_hash=None,  
        downloader=_HTTPDownloader(progressbar=True),
        path=_os_cache('gplately'),
    )        
    feature_filenames = []
    if file_ext is not None:
        if fname.endswith(file_ext):
            if substring is not None:
                if fname.lower().find(substring) != -1:
                    feature_filenames.append(fname)
            else:
                feature_filenames.append(fname)              
    else:
        if substring is not None:
            if fname.lower().find(substring) != -1:
                feature_filenames.append(fname)
        else:
            feature_filenames.append(fname)

    feature_filenames = ignore_macOSX(feature_filenames)
    return feature_filenames


def _extract_geom(file_collection, database_link, feature_type):
    """Downloads topology geometries stored in a zip folder or a single-file download link. 

    Checks the GPlately Data Server for an zip folder OR single-file download link. Muller et al. 2019
    data, for example, are all contained within one zip folder.

    By default, .gpml topologies whose filenames include the 'feature_type' substring  are searched for. 
    If they cannot be located, this module will attempt to search for .shp (and corresponding extension)
    equivalents. 

    If several files are downloaded from individual links (i.e. if .shp and its extensions are held in
    unique download links on the GPlately server), Pooch will register unique hashes for each file and will
    concatenate them onto the cached filenames. This is problematic for pygplates as it needs .shp files to
    have consistent filenames with its extensions. This method slices the final filename, taking the hashes 
    out and concatenating the original filenames with the full cache path.

    Parameters
    ----------
    file_collection : str
        A string to classify the file collection to extract data from (i.e. "Seton2012").
    database_link : list
        A list containing the full link to a single zip folder download URL, or a series of download links.
    feature_type : str
        A substring to use to sort through lots of filenames (i.e. "coastlines" to extract coastlines from a
        zip folder). 

    Returns
    -------
    geometries : list
        A list of full paths to downloaded topology geometries.
    """
    geometries = []
    if database_link is not None:
        
        # If there is one link for this file collection, it is assumed to be a zip folder link.
        if len(database_link) == 1:
            if database_link.endswith(".zip"):
                # Searches for gpml geometries by default... if it cannot be found, .shp will be
                # searched for instead. 
                geometries = fetch_from_zip(database_link, ".gpml", feature_type)

        # If there are >1 links in this list, loop through all links and download them.
        else:
            filenames = []
            for url in database_link:
                filename = fetch_from_single_link(url)
                filenames.append(filename[0])
                # Filepaths will each have an embedded hash; removes them to ensure consistency in filenames
                # Get the path to the cache
                #print(filenames[0][0])
                    
        
            is_gpml = any(".gpml" in fname for fname in filenames)
            if not is_gpml:
                print("No .gpml %s features found in %s. Attempting to find .shp instead" % (feature_type, file_collection))
                for index, fname in enumerate(filenames):
                    split_paths = fname.split("-")
                    cache_path = split_paths[0][:-32]
                    new_path = cache_path + split_paths[1]
                    os.rename(fname, new_path)
                    if fname.endswith(".shp"):
                        geometries.append(new_path)
                        print("Found a %s file with a .shp extension." %(feature_type))
            else:
                for fname in filenames:
                    if fname.endswith(".gpml"):
                        geometries.append(fname)
                        
    else:
        print("The %s collection has no %s files." % (file_collection, feature_type))

    geometries = ignore_macOSX(geometries)
    return geometries


class DataServer(object):

    def __init__(self, file_collection):
        """ Constructs all necessary attributes for the DataServer object.

        Parameters
        ----------
        file_collection : str
            A string to classify the file collection to extract data from (i.e. "Seton2012"). 
        """
        self.file_collection = file_collection


    def get_plate_reconstruction_files(self):
        """Extracts and downloads rotation files, topology files and static polygons from a 
        certain data collection attributed to the DataServer object (i.e. "Muller2019"), if it exists in the 
        GPlately database. Constructs a Pygplates rotation model and feature collection from extracted files.
        
        A rotation model, a topology feature collection and some static polygons are all attributes for GPlately's
        PlateReconstruction object. Note that .gpml topologies and static polygons are searched for by default. If
        the specified data collection doesn't have these, ESRI shapefiles (.shp) and their corresponding file extensions
        will be searched for instead. The user will be alerted if a certain geometry type does not exist in the current
        database.
            
        Returns
        -------
        files : tuple
            Contains 3 lists that each contain:
            - the pygplates rotation model;
            - the pygplates topology feature follection; and
            - the full path to static polygons
            as long as they exist in the specified data collection.
            
        Raises
        ------
        ValueError
            If a file collection to fetch was not supplied.
        General alerts
            If a certain geometry does not exist for a certain collection (i.e. one collection is missing COBs), the 
            user will be alerted.
            If a gpml geometry could not be found, a shapefile equivalent (and its associated file extensions) will
            be found and returned instead. The user will be alerted.
        """
        if self.file_collection is None:
            raise ValueError("Please supply a file collection to fetch.")
        #
        #
        #
        #
        #                                           GPLATELY - ROTATION MODEL FILE SERVER
        #
        # A dictionary of EarthByte plate model data available for the user from WebDAV (append this if there is a needed collection!).
        # Keys are collection names that are ascribed a list to download links. If there is only one link for a collection, it
        # is a link to one zip folder that encloses:
        # - a rotation model file
        # - a set of topology features
        # - static polygons
        #
        # If a collection has more than one link, its files are downloadable from unique links instead of a single zip folder.
        # Such a list takes the general form:
        # 
        # [rotation model download link,
        #  topology_feature download link,
        #  static_polygon download link]
        #
        # If there is no download link for a specific plate model file, it is filled with "None". The user will be alerted if this is the case. 
        #
        #
        #
        #
        #
        #
        
        database = {"Muller2019" : ["https://www.earthbyte.org/webdav/ftp/Data_Collections/Muller_etal_2019_Tectonics/Muller_etal_2019_PlateMotionModel/Muller_etal_2019_PlateMotionModel_v2.0_Tectonics.zip"], 
                    "Seton2012" : ["https://www.earthbyte.org/webdav/ftp/Data_Collections/Seton_etal_2012_ESR/Rotations/Seton_etal_ESR2012_2012.1.rot",
                                   "https://www.earthbyte.org/webdav/ftp/Data_Collections/Seton_etal_2012_ESR/Plate_polygons/Seton_etal_ESR2012_PP_2012.1.gpml",
                                  None], 
                    "Merdith2021" : ["https://zenodo.org/record/4320873/files/SM2-Merdith_et_al_1_Ga_reconstruction.zip?download=1"],
                    "Matthews2016" : ["https://www.earthbyte.org/webdav/ftp/Data_Collections/Matthews_etal_2016_Global_Plate_Model_GPC.zip"], 
                    "Merdith2017" : ["https://www.earthbyte.org/webdav/ftp/Data_Collections/Merdith_etal_2017_GR.zip"], 
                   }

        # Set to true if we find the given collection in our database
        found_collection = False
        for collection, zip_url in database.items():

            # Only continue if the user's chosen collection exists in our database
            if self.file_collection.lower() == collection.lower():
                found_collection = True
                rotation_filenames = []
                topology_features = pygplates.FeatureCollection()
                static_polygons = []

                # If there is only one zip folder under the collection name, we assume everything we need is contained
                # inside it. Continue
                if len(zip_url) == 1:
                    rotation_filenames = fetch_from_zip(zip_url[0], ".rot")
                    rotation_model = pygplates.RotationModel(rotation_filenames)
                    
                    topology_filenames = fetch_from_zip(zip_url[0], ".gpml")
                    for file in topology_filenames:
                        if "Inactive" not in file:
                            topology_features.add(pygplates.FeatureCollection(file))
                            
                    static_polygons = fetch_from_zip(zip_url[0], ".gpml", "static")
                   
                    files = rotation_model, topology_features, static_polygons

                # If the collection is not contained in a single zip folder, download data from all unique zip 
                # folders/files (i.e. as is for Seton2012)
                else:
                    # If the rotation models exist and are contained in their own zip file
                    if zip_url[0] is not None:
                        rotation_filenames = fetch_from_single_link(zip_url[0], ".rot")  
                        rotation_model = pygplates.RotationModel(rotation_filenames)                
                    else:
                        print("The %s collection has no .rot files." % (self.file_collection))

                    # If gpml feature topologies exist for this data collection and are contained in a zip file
                    if zip_url[1] is not None:
                        topology_filenames = fetch_from_single_link(zip_url[1], ".gpml")
                        for topology in topology_filenames:
                            if "Inactive" not in topology:
                                topology_features.add(pygplates.FeatureCollection(topology))                 
                    else:
                        print("The %s collection has no topology files." % (self.file_collection))

                    # If static polygons exist for this data collection, download it.
                    if zip_url[2] is not None:
                        static_polygons = fetch_from_single_link(zip_url[2], ".gpml", "static") 
                        
                        # might reconsider this if we want gpml by default
                        for statpoly in static_polygons:
                            if statpoly.endswith(".shp"): 
                                if statpoly.lower().find("static") != -1:
                                    static_polygons.append(statpoly)                       
                    else:
                        print("The %s collection has no static polygon files." % (self.file_collection))
                    files = rotation_model, topology_features, static_polygons

                # Break the loop once all plate model data have been extracted
                break

        # If `found_collection` is still false, the given collection was not found in the database
        if found_collection is False: 
            raise ValueError("%s not in collection database." % (self.file_collection))

        return files


    def get_topology_geometries(self):
        """Extracts and downloads gpml (or .shp if .gpml not available) coastline, continent and COB geometries from a 
        certain data collection attributed to the DataServer object (i.e. "Muller2019"), if it exists in the 
        GPlately database.
        
        Coastline, continent and COB geometries are all necessary attributes for GPlately's PlotTopologies object. 
        Note that if a .gpml file could not be found, an ESRI shapefile (.shp) and its corresponding file extensions will be
        searched for instead. The user will be alerted if a certain geometry type does not exist in the current database.
            
        Returns
        -------
        files : tuple
            Contains 3 lists that each contain complete file paths to:
            - the coastline geometries;
            - the continental geometries; and
            - the COB geometries
            as long as they exist in the specified data collection.
            
        Raises
        ------
        ValueError
            If a file collection to fetch was not supplied.
        General alerts
            If a certain geometry does not exist for a certain collection (i.e. one collection is missing COBs), the 
            user will be alerted.
            If a gpml geometry could not be found, a shapefile equivalent (and its associated file extensions) will
            be found and returned instead. The user will be alerted.
        """
        
        if self.file_collection is None:
            raise ValueError("Please supply a file collection to fetch.")

        #
        #                                        GPLATELY - GEOMETRY FILE SERVER
        #
        # A list of EarthByte polygon and polyline geometries available for extraction (append this if there is a needed collection!).
        # Dictionary values are lists of zip file URLs from EarthByte's WebDAV server. If a list has one URL, it is a zip folder containing
        # all three geometries. Conversely, a single collection can be ascribed 3 lists each containing unique download links to geometries.
        #
        #
        #
        #
        #
        #
        #
        database = {"Muller2019" : ["https://www.earthbyte.org/webdav/ftp/Data_Collections/Muller_etal_2019_Tectonics/Muller_etal_2019_PlateMotionModel/Muller_etal_2019_PlateMotionModel_v2.0_Tectonics.zip"], 
                    "Seton2012" : [["https://www.earthbyte.org/webdav/ftp/Data_Collections/Seton_etal_2012_ESR/Coastlines/Seton_etal_ESR2012_Coastline_2012.1.gpml",
                                   "https://www.earthbyte.org/webdav/ftp/Data_Collections/Seton_etal_2012_ESR/Coastlines/Seton_etal_ESR2012_Coastline_2012.1_polyline.dbf",
                                   "https://www.earthbyte.org/webdav/ftp/Data_Collections/Seton_etal_2012_ESR/Coastlines/Seton_etal_ESR2012_Coastline_2012.1_polyline.kml",
                                   "https://www.earthbyte.org/webdav/ftp/Data_Collections/Seton_etal_2012_ESR/Coastlines/Seton_etal_ESR2012_Coastline_2012.1_polyline.prj",
                                   "https://www.earthbyte.org/webdav/ftp/Data_Collections/Seton_etal_2012_ESR/Coastlines/Seton_etal_ESR2012_Coastline_2012.1_polyline.shp",
                                   "https://www.earthbyte.org/webdav/ftp/Data_Collections/Seton_etal_2012_ESR/Coastlines/Seton_etal_ESR2012_Coastline_2012.1_polyline.shx"],
                                   None,
                                   ["https://www.earthbyte.org/webdav/ftp/Data_Collections/Seton_etal_2012_ESR/Continent-ocean_boundaries/Seton_etal_ESR2012_ContinentOceanBoundaries_2012.1.dbf",
                                   "https://www.earthbyte.org/webdav/ftp/Data_Collections/Seton_etal_2012_ESR/Continent-ocean_boundaries/Seton_etal_ESR2012_ContinentOceanBoundaries_2012.1.gpml",
                                   "https://www.earthbyte.org/webdav/ftp/Data_Collections/Seton_etal_2012_ESR/Continent-ocean_boundaries/Seton_etal_ESR2012_ContinentOceanBoundaries_2012.1.kml",
                                   "https://www.earthbyte.org/webdav/ftp/Data_Collections/Seton_etal_2012_ESR/Continent-ocean_boundaries/Seton_etal_ESR2012_ContinentOceanBoundaries_2012.1.prj",
                                   "https://www.earthbyte.org/webdav/ftp/Data_Collections/Seton_etal_2012_ESR/Continent-ocean_boundaries/Seton_etal_ESR2012_ContinentOceanBoundaries_2012.1.shp",
                                   "https://www.earthbyte.org/webdav/ftp/Data_Collections/Seton_etal_2012_ESR/Continent-ocean_boundaries/Seton_etal_ESR2012_ContinentOceanBoundaries_2012.1.shx"]], 
                    "Merdith2021" : ["https://zenodo.org/record/4320873/files/SM2-Merdith_et_al_1_Ga_reconstruction.zip?download=1"],
                    "Matthews2016" : ["https://www.earthbyte.org/webdav/ftp/Data_Collections/Matthews_etal_2016_Global_Plate_Model_GPC.zip"], 
                    "Merdith2017" : ["https://www.earthbyte.org/webdav/ftp/Data_Collections/Merdith_etal_2017_GR.zip"],              
                   }

        # Set to true if we find the given collection in our database
        found_collection = False
        for collection, zip_url in database.items():

            # Only continue if the user's chosen collection exists in our database
            if self.file_collection.lower() == collection.lower():
                found_collection = True
                coastlines = []
                continents = []
                COBs = []

                if len(zip_url) == 1:
                    coastlines = fetch_from_zip(zip_url[0], ".gpml", "coastline")
                    continents = fetch_from_zip(zip_url[0], ".gpml", "continent")
                    COBs = fetch_from_zip(zip_url[0], ".gpml", "cob")                   
                    files = coastlines, continents, COBs

                # If the collection is not contained in a single zip folder, download data from all unique zip 
                # folders/files (i.e. as is for Seton2012)
                else:                
                    coastlines = _extract_geom(self.file_collection, zip_url[0], "coastline")               
                    continents = _extract_geom(self.file_collection, zip_url[1], "continent")
                    COBs = _extract_geom(self.file_collection, zip_url[2], "cob")                               
                    files = coastlines, continents, COBs
                                    
                # Break the loop once all plate model data have been extracted
                break

        # If `found_collection` is still false, the given collection was not found in the database
        if found_collection is False: 
            raise ValueError("%s not in collection database." % (self.file_collection))

        return files


    def get_netcdf_rasters(self, time=None):
        """Downloads netCDF rasters stored in GPlately's DataServer from a web server. These rasters are optimal for use 
        in GPlately's Raster object. To access rasters from a certain data collection, pass a label (i.e. "Muller2019") to
        the DataServer object. 

        Returns
        -------
        raster_filenames : list of str
            A list of all netCDF rasters for each Ma belonging to a particular data collection. The file path strings are
            ordered from recent to deep geological time (Ma).
        time : int, default None
            Choose whether to return a netCDF grid at a particular geological time. By default the full list of agegrid
            file paths is returned. 

        Raises
        ------
        ValueError
            If a data collection label is not supplied to the DataServer object. 
        """
        if self.file_collection is None:
            raise ValueError("Please supply a file collection to fetch.")

        #
        # ---------------------------------- GPLATELY RASTER DATA SERVER ---------------------------------------
        # A list of EarthByte rasters available for extraction (append this if there is a needed collection!).
        # Dictionary values are lists of zip file URLs from EarthByte's WebDAV server. If a list has one URL, it is a zip folder all raster
        # grids belonging to a particular data collection.
        #
        database = {"Muller2019" : ["https://www.earthbyte.org/webdav/ftp/Data_Collections/Muller_etal_2019_Tectonics/Muller_etal_2019_Agegrids/Muller_etal_2019_Tectonics_v2.0_netCDF.zip"]
           }

        # Set to true if we find the given collection in database
        found_collection = False
        for collection, zip_url in database.items():

            # Only continue if the user's chosen collection exists in database
            if self.file_collection.lower() == collection.lower():
                found_collection = True

                # If there is only one link under the collection name, assume all rasters are contained in it
                raster_filenames = fetch_from_zip(zip_url[0], ".nc")
            break

            if found_collection is False: 
                raise ValueError("%s not in collection database." % (self.file_collection))

        raster_filenames = order_filenames_by_time(raster_filenames)

        if time is None:
            return raster_filenames
        else:
            return raster_filenames[time]


