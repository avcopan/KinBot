###################################################
##                                               ##
## This file is part of the KinBot code v2.0     ##
##                                               ##
## The contents are covered by the terms of the  ##
## BSD 3-clause license included in the LICENSE  ##
## file, found at the root.                      ##
##                                               ##
## Copyright 2018 National Technology &          ##
## Engineering Solutions of Sandia, LLC (NTESS). ##
## Under the terms of Contract DE-NA0003525 with ##
## NTESS, the U.S. Government retains certain    ##
## rights to this software.                      ##
##                                               ##
## Authors:                                      ##
##   Judit Zador                                 ##
##   Ruben Van de Vijver                         ##
##                                               ##
###################################################
import numpy as np
import copy
import time
import math

from vector import *
from qc import *
from constants import *
from kinbot import *
from stationary_pt import *
from geom import *
from qc import *
from reac_family import *
import par



def do_r12_insertion_R(species, instance, step, instance_name):
    """
    Carry out the reaction.
    """
    
    if step > 0:
        if check_qc(instance_name) != 'normal' and check_qc(instance_name) != 'error': return step
    
    #maximum number of steps for this reaction family
    max_step = 12

    # have a look at what has been done and what needs to be done
    step,geom, kwargs = initialize_reaction(species, instance, step, instance_name, max_step)

    #the the constraints for this step
    step, fix, change, release = get_constraints_r12_insertion_R(step, species, instance,geom)
    
    #carry out the reaction and return the new step
    return carry_out_reaction(species, instance, step, instance_name, max_step, geom, kwargs, fix, change, release)   
            
def get_constraints_r12_insertion_R(step,species,instance,geom):
    """
    There are three types of constraints:
    1. fix a coordinate to the current value
    2. change a coordinate and fix is to the new value
    3. release a coordinate (only for gaussian)
    """
    fix = []
    change = []
    release = []
    #if step < 12:
    #    #fix all the bond lengths
    #    for i in range(par.natom - 1):
    #        for j in range(i+1, par.natom):
    #            if species.bond[i][j] > 0:
    #                fix.append([i+1,j+1])
    if step < 12:
        
        fval = [1.67,2.2,1.9]
        
        if par.atom[instance[0]] == 'H':
            fval = [1.7,1.09,2.2]
        if par.atom[instance[2]] == 'H': 
            fval = [2.2,1.09,1.7]
        if par.atom[instance[0]] == 'O' or par.atom[instance[2]] == 'O': 
            fval[1] = 1.8

        val = new_bond_length(species,instance[0],instance[1],step+1,12,fval[0],geom)
        constraint = [instance[0] + 1,instance[1] + 1,val]
        change.append(constraint)
        
        val = new_bond_length(species,instance[1],instance[2],step+1,12,fval[1],geom)
        constraint = [instance[1] + 1,instance[2] + 1,val]
        change.append(constraint)
        
        val = new_bond_length(species,instance[2],instance[0],step+1,12,fval[2],geom)
        constraint = [instance[2] + 1,instance[0] + 1,val]
        change.append(constraint)

    
    #remove the bonds from the fix if they are in another constaint
    for c in change:
        if len(c) == 3:
            index = -1
            for i,fi in enumerate(fix):
                if len(fi) == 2:
                    if sorted(fi) == sorted(c[:2]):
                        index = i
            if index > -1:
                del fix[index]
    
    return step, fix, change, release
    
