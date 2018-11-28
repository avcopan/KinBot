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

"""
This is the main class to run KinBot to explore
a full PES instead of only the reactions of one well
"""
from __future__ import print_function
import sys
import os
import logging
import datetime
import time
import subprocess
import json
from distutils.dir_util import copy_tree

from ase.db import connect

import constants
import license_message
from parameters import Parameters
from stationary_pt import StationaryPoint


def main():
    input_file = sys.argv[1]
    
    #print the license message to the console
    print(license_message.message)

    #initialize the parameters
    par = Parameters(input_file)
    
    # set up the logging environment 
    logging.basicConfig(filename='pes.log',level=logging.INFO)
    
    logging.info(license_message.message)
    logging.info('Starting the PES search at %s'%(datetime.datetime.now()))
 
    well0 = StationaryPoint('well0', par.par['charge'], par.par['mult'], smiles = par.par['smiles'], structure = par.par['structure'])
    well0.characterize()
    write_input(par,well0,par.par['barrier_threshold'],os.getcwd())
    
    f = open('chemids','w')
    f.write(str(well0.chemid) + '\n')
    f.close()
   
    max_running = 1
    running = []
    finished = []
    jobs = []
    pids = {}
    while 1:
        j = len(jobs)
        f = open('chemids','r')
        jobs = f.read().split('\n')
        jobs = [ji for ji in jobs if ji != '']
        f.close()
        
        if len(jobs) > j:
            logging.info('Picked up new jobs: ' + ' '.join([ji for ji in jobs[j:]]))

        if len(finished) == len(jobs):
            break
        
        while len(running) < max_running and len(running) + len(finished) < len(jobs):
            #start a new job
            job = jobs[len(running) + len(finished)]
            pid = submit_job(job)
            pids[job] = pid
            running.append(job)
        #check if a thread is done
        for job in running:
            if not check_status(job,pids[job]):
                finished.append(job)
        #remove the finished threads
        for job in finished: 
            if job in running:
                running.remove(job)
        f = open('pes_summary.txt','w+')
        f.write('Total\t\t%i\n'%len(jobs))
        f.write('Running\t\t%i\n'%len(running))
        f.write('Finished\t%i\n\n'%len(finished))
        for job in finished: 
            f.write('\t%s\n'%job)
        
        f.close()
        time.sleep(1)
    postprocess(par,jobs)

def postprocess(par,jobs):
    #list of lists with four elements
    # reactant chemid
    # reaction name
    # products chemid list
    # reaction barrier height
    reactions = [] 
    wells = []
    products = []
    #read all the jobs
    for ji in jobs:
        summary = open(ji + '/summary_' + ji + '.out','r').readlines()
        for line in summary:
            if line.startswith('SUCCESS'):
                pieces = line.split()
                reactant = ji
                ts = pieces[2]
                prod = pieces[3:]
                barrier = float(pieces[1])
                
                if not reactant in wells:
                    wells.append(reactant)
                if len(prod) == 1:
                    if not prod[0] in wells:
                        wells.append(prod[0])
                else:
                    if not '_'.join(sorted(prod)) in products:
                        products.append('_'.join(sorted(prod)))
                new = 1
                temp = None
                for i,rxn in enumerate(reactions):
                    if reactant == rxn[0] and '_'.join(sorted(prod)) == '_'.join(sorted(rxn[2])):
                        new = 0
                        temp = i
                    if reactant == ''.join(rxn[2]) and ''.join(prod) == rxn[0]:
                        new = 0
                        temp = i
                if new:
                    reactions.append([reactant,ts,prod,barrier])
                else:
                    #check if the previous reaction has a lower energy or not
                    if reactions[i][3] > barrier:
                        reactions.pop(temp)
                        reactions.append([reactant,ts,prod,barrier])
    zero_energy = get_energy(jobs[0], jobs[0],0,par.par['high_level'])
    zero_zpe = get_zpe(jobs[0], jobs[0],0,par.par['high_level'])
    #copy xyz files
    copy_xyz(wells)
    
    #write pes input
    create_pesviewer_input(par, jobs[0], wells, products, reactions, zero_energy, zero_zpe, par.par['high_level'])
    
    #write_mess
    create_mess_input(par, jobs[0], wells, products, reactions, zero_energy, zero_zpe, par.par['high_level'])


def copy_xyz(wells):
    dir_xyz = 'xyz/'
    if not os.path.exists(dir_xyz):
        os.mkdir(dir_xyz)
    for well in wells:
        copy_tree(well + '/xyz/', dir_xyz)

    
def get_rxn(prods,rxns):
    for rxn in rxns:
        if prods == '_'.join(sorted(rxn[2])):
            return rxn


def create_mess_input(par, well0, wells, products, reactions, zero_energy, zero_zpe, high_level):
    fname = 'input.mess'
    f = open(fname, 'w+')
    #todo: add header
    
    s = '##############\n'
    s += '# WELLS \n'
    s += '##############\n'
    
    for well in wells:
        energy = get_energy(well,well,0,par.par['high_level'])
        zpe = get_zpe(well,well,0,par.par['high_level'])
        zeroenergy = (  ( energy + zpe )- ( zero_energy + zero_zpe) ) * constants.AUtoKCAL
        s += open(well + '/' + well + '.mess').read().format(zeroenergy = zeroenergy) 
        
    for prods in products:
        energy = 0.
        zpe = 0.
        rxn = get_rxn(prods,reactions)
        for pr in prods.split('_'):
            energy += get_energy(rxn[0],pr,0,par.par['high_level'])
            zpe += get_zpe(rxn[0],pr,0,par.par['high_level'])
        zeroenergy = (  ( energy + zpe )- ( zero_energy + zero_zpe) ) * constants.AUtoKCAL
        s += open(rxn[0] + '/' + prods + '.mess').read().format(ground_energy = zeroenergy) 
    f.write('\n')
    
    f.write(s)
    f.close()
    

def create_pesviewer_input(par, well0, wells, products, reactions, zero_energy, zero_zpe, high_level):
    fname = 'pesviewer.inp'
    
    f = open(fname,'w+')
    f.write("> <comments>")
    f.write(license_message.message)
    
    f.write("""This comment is not interpreted, so store any extra info here.
Keywords are case insensitive. Look at the help below.
IMPORTANT: avoid the use of '2d' and '3d' in the names of species, transition states and reactions
(these strings are employed when generating the 2d and 3d files of the molecules)
If you want to use 3D coordinates, store them in a xyz/ directory in the same directory as the python script""")
    f.write('\n\n')
    
    f.write('> <id> Potential_energy_surface\n\n')
    f.write("""> <options> 
units              kcal/mol  #energy units
use_xyz            1         # use xyz, put 0  to switch off
rescale            0         # no rescale , put the well or bimolecular name here to rescale to that value
fh                 9.        # figure height
fw                 18.       # figure width
margin             0.2       # margin fraction on the x and y axis
dpi                120       # dpi of the molecule figures
save               0         # does the plot need to be saved (1) or displayed (0)
write_ts_values    1         # booleans tell if the ts energy values should be written
write_well_values  1         # booleans tell if the well and bimolecular energy values should be written
bimol_color        red       # color of the energy values for the bimolecular products
well_color         blue      # color of the energy values of the wells
ts_color           green     # color or the energy values of the ts, put to 'none' to use same color as line
show_images        1         # boolean tells whether the molecule images should be shown on the graph
rdkit4depict       1         # boolean that specifies which code was used for the 2D depiction""")
    f.write('\n\n')
    
    f.write('> <wells> \n')
    for well in wells:
        well_energy = get_energy(well,well,0,par.par['high_level'])
        well_zpe = get_zpe(well,well,0,par.par['high_level'])
        energy = (well_energy + well_zpe - zero_energy - zero_zpe) * constants.AUtoKCAL
        f.write('%s %.2f\n'%(well,energy))
    f.write('\n')
    
    f.write('> <bimolec> \n')
    for prods in products:
        energy = 0. - zero_energy - zero_zpe
        rxn = get_rxn(prods,reactions)
        for pr in prods.split('_'):
            energy += get_energy(rxn[0],pr,0,par.par['high_level'])
            energy += get_zpe(rxn[0],pr,0,par.par['high_level'])
        energy = energy * constants.AUtoKCAL
        f.write('%s %.2f\n'%(prods,energy))
    f.write('\n')
    
    f.write('> <ts> \n')
    for rxn in reactions:
        mp2 = 0
        if 'R_Addition_MultipleBond' in rxn[1] and not par.par['high_level']:
            mp2 = 1
        well_energy = get_energy(rxn[0],rxn[0],0,par.par['high_level'], mp2)
        well_zpe = get_zpe(rxn[0],rxn[0],0,par.par['high_level'], mp2)
        ts_energy = get_energy(rxn[0],rxn[1],1,par.par['high_level'])
        ts_zpe = get_zpe(rxn[0],rxn[1],1,par.par['high_level'])
        energy = (ts_energy + ts_zpe - well_energy - well_zpe) * constants.AUtoKCAL
        prod_name = '_'.join(sorted(rxn[2]))
        f.write('%s %.2f %s %s\n'%(rxn[1],energy,rxn[0],prod_name))
    f.write('\n')
    
    f.write('> <barrierless> \n\n')
    
    f.write("""> <help>
File follows the rules of SD file format for keywords. Keywords are case
insensitive when parsed.
Keywords:
units: units of the energies supplied above

usexyz: use the xyz coordinates of all the species and render a 2D/3D depiction

rescale: energies are rescaled relative to the energy of the species given here 

wells: all the wells of the PES, separated by lines
each line contains the name, the energy, and optionally the smiles

bimolec: all the bimolecular products of the PES, separated by lines
each line contains the name, the energy, and optionally the smiles of both bimolecular products

ts: all the transition states of the PES, separated by lines
each line contains the name, the energy, and the names of the reactant and product

barrierless: all the barrierless reactions of the PES, separated by lines
each line contains the name and the names of the reactant and product""")
    f.close()


def get_energy(dir,job,ts,high_level,mp2=0):
    db = connect(dir + '/kinbot.db')
    if ts:
        j = job
    else:
        j = job + '_well'
    if mp2:
        j += '_mp2'
    if high_level:
        j += '_high'
    
    rows = db.select(name = j)
    for row in rows:
        if hasattr(row, 'data'):
            energy = row.data.get('energy')
    #ase energies are always in ev, convert to hartree
    energy *= constants.EVtoHARTREE
    return energy


def get_zpe(dir,job,ts,high_level,mp2=0):
    db = connect(dir + '/kinbot.db')
    if ts:
        j = job
    else:
        j = job + '_well'
    if mp2:
        j += '_mp2'
    if high_level:
        j += '_high'
    
    rows = db.select(name = j)
    for row in rows:
        if hasattr(row, 'data'):
            zpe = row.data.get('zpe')

    return zpe


def check_status(job,pid):
    command = ['ps', '-u', 'root', '-N', '-o', 'pid,s,user,%cpu,%mem,etime,args']
    process = subprocess.Popen(command,shell=False,stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    out,err = process.communicate()
    out = out.decode()
    lines = out.split('\n')
    for line in lines:
        if len(line)> 0:
            if '%i'%pid == line.split()[0]:
                return 1
    return 0


def submit_job(chemid):
    """
    Submit a kinbot run usung subprocess and return the pid
    """
    command = ["kinbot", chemid + ".json", "&"]
    outfile = open('{dir}/kinbot.out'.format(dir=chemid), 'w')
    errfile = open('{dir}/kinbot.err'.format(dir=chemid), 'w')
    process = subprocess.Popen(command,cwd = chemid, stdout=outfile, stdin=subprocess.PIPE, stderr=errfile)
    time.sleep(1)
    pid = process.pid
    return pid 


def write_input(par,species,threshold,root):
    #directory for this particular species
    dir = root + '/' + str(species.chemid) + '/'
    if not os.path.exists(dir):
        os.makedirs(dir)
    
    #make a new parameters instance and overwrite some keys
    par2 = Parameters(par.input_file)
    #overwrite the title
    par2.par['title'] = str(species.chemid)
    #make a structure vector and overwrite the par structure
    structure = []
    for at in range(species.natom):
        pos = species.geom[at]
        sym = species.atom[at]
        structure += [sym,pos[0],pos[1],pos[2]]
    par2.par['structure'] = structure
    #delete the par smiles
    par2.par['smiles'] = ''
    #overwrite the barrier treshold
    par2.par['barrier_threshold'] = threshold
    #set the pes option to 1
    par2.par['pes'] = 1
    
    file_name = dir + str(species.chemid) + '.json'
    with open(file_name,'w') as outfile:
        json.dump(par2.par,outfile,indent = 4, sort_keys = True)
    
if __name__ == "__main__":
    main()

