import abc
from typing import List

import pygplates


class FeatureFilter(metaclass=abc.ABCMeta):
    @classmethod
    def __subclasshook__(cls, subclass):
        return (
            hasattr(subclass, "should_keep")
            and callable(subclass.should_keep)
            or NotImplemented
        )

    @abc.abstractmethod
    def should_keep(self, feature: pygplates.Feature) -> bool:
        """This abstract method must be implemented in subclass.

        :param feature: pygplates.Feature

        :returns: true if the feature should be kept; false otherwise
        """

        raise NotImplementedError


class FeatureNameFilter(FeatureFilter):
    """filter features by name

    for example:
        FeatureNameFilter(['Africa', 'Asia']) -- keep features who name contains 'Africa' or 'Asia'
        FeatureNameFilter(['Africa', 'Asia'], exclude=True) -- keep features who name does not contain 'Africa' or 'Asia'
        FeatureNameFilter(['Africa', 'Asia'], exact_match=True) -- keep features who name is 'Africa' or 'Asia'
        FeatureNameFilter(['Africa', 'Asia'], exclude=True, exact_match=True) -- keep features who name is not 'Africa' or 'Asia'
        FeatureNameFilter(['Africa', 'Asia'], exclude=True, exact_match=True, case_sensitive=True) -- keep features who name is not 'Africa' or 'Asia' (case sensitive)
    """

    def __init__(
        self, names: List[str], exact_match=False, case_sensitive=False, exclude=False
    ):
        self.names = names
        self.exact_match = exact_match
        self.case_sensitive = case_sensitive
        self.exclude = exclude

    def check_name(self, name_1: str, name_2: str) -> bool:
        """check if two names are the same or name_2 contains name_1"""
        if not self.case_sensitive:
            name_1_tmp = name_1.lower()
            name_2_tmp = name_2.lower()
        else:
            name_1_tmp = name_1
            name_2_tmp = name_2
        if self.exact_match:
            return name_1_tmp == name_2_tmp
        else:
            return name_1_tmp in name_2_tmp

    def should_keep(self, feature: pygplates.Feature) -> bool:
        if self.exclude:
            for name in self.names:
                if self.check_name(name, feature.get_name()):
                    return False
            return True
        else:
            for name in self.names:
                if self.check_name(name, feature.get_name()):
                    return True
            return False


class PlateIDFilter(FeatureFilter):
    """filter features by plate ID

    for example:
        PlateIDFilter([101,201,301]) -- keep features whose plate id is 101 or 201 or 301
        PlateIDFilter([101,201,301], exclude=True) -- keep features whose plate id is not 101 nor 201 nor 301

    """

    def __init__(self, pids: List[int], exclude=False):
        self.pids = pids
        self.exclude = exclude

    def should_keep(self, feature: pygplates.Feature) -> bool:
        if not self.exclude and feature.get_reconstruction_plate_id() in self.pids:
            return True
        if self.exclude and feature.get_reconstruction_plate_id() not in self.pids:
            return True
        return False


class BirthAgeFilter(FeatureFilter):
    """filter features by the time of appearance

    for example:
        BirthAgeFilter(500) -- keep features whose time of apprearance are bigger than 500
         BirthAgeFilter(500, keep_older=False) --  keep features whose time of apprearance are smaller than 500

    :param age: the age criterion
    :param keep_older: if True, return True when the feature's birth age is older than the age criterion. If False, otherwise.

    """

    def __init__(self, age: float, keep_older=True):
        self.age = age
        self.keep_older = keep_older

    def should_keep(self, feature: pygplates.Feature) -> bool:
        valid_time = feature.get_valid_time(None)
        if valid_time:
            if self.keep_older and valid_time[0] > self.age:
                return True
            if not self.keep_older and valid_time[0] < self.age:
                return True
        return False


def filter_feature_collection(
    feature_collection: pygplates.FeatureCollection, filters: List[FeatureFilter]
):
    """the loop to apply fiters"""
    new_feature_collection = pygplates.FeatureCollection()
    for feature in feature_collection:
        keep_flag = True
        for filter in filters:
            if not filter.should_keep(feature):
                keep_flag = False
                break
        if keep_flag:
            new_feature_collection.add(feature)
    return new_feature_collection
