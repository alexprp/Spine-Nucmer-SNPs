#!/usr/bin/env python3

import sys
import os
import re
import time
import argparse
import pickle
import gzip
from collections import defaultdict

start = time.time()

class snps_object():
	"""
	Stores header and seq of fasta as well as positional information about indels.

	
	Attributes:
		genomeid (str): id of the genome with these snps.
		snps (dict): dict for snps with the following structure { scaffold : { position : snp, { position : {position_in_indel : snp } } } }
	"""
	def __init__(self,genomeid):
		self.genomeid = genomeid
		self.snps = {}


def parse_snps(ref_fasta, ref_snps_obj, file, genomeid):
	"""
	Args:
		ref_fasta (dict): dict with the reference genome {contig_name: sequence}.
		ref_snps_obj (snps_object): snps_object class instance for the reference core genome.
		file (str): Path to snps file to be parsed.
		genomeid (str): ID to use to identify this snps file and its associated snps_object.

	Returns:
		(tuple) ref_snps_obj, query_snps_obj 
		ref_snps_object with sites that were variant in this file added.
		query_snps_obj representing the variant sites found in this file.
	"""
	indel_counter = 1
	indel_pos = 0	
	query_snps_obj = snps_object(genomeid)
	with open(file, 'r') as insnps:
		for line in insnps.readlines()[5:]:


			backbone = line.split()[13]
			pos = int(line.split()[0])
			refnuc = line.split()[1]
			quernuc = line.split()[2]


			if backbone not in ref_snps_obj.snps:
				indel_counter = 1
				ref_snps_obj.snps[backbone] = {}

			if backbone not in query_snps_obj.snps:
				indel_counter = 1
				query_snps_obj.snps[backbone] = {}

			if refnuc != ".":
				indel_counter = 1 # If the indel is finished, reset the indel_counter that measures indel size
				if pos not in ref_snps_obj.snps[backbone]:
					ref_snps_obj.snps[backbone][pos] = refnuc
				else:
					if isinstance(ref_snps_obj.snps[backbone][pos],dict):
						if 0 not in ref_snps_obj.snps[backbone][pos].keys():
							ref_snps_obj.snps[backbone][pos][0] = refnuc
				query_snps_obj.snps[backbone][pos] = quernuc



			if refnuc == ".":
				
				if pos == indel_pos:
					indel_counter += 1
				else:
					indel_pos = int(pos)
					indel_counter = 1

				if pos in ref_snps_obj.snps[backbone]:

					if isinstance(ref_snps_obj.snps[backbone][pos],dict):
						if not indel_counter in ref_snps_obj.snps[backbone][pos]:
							ref_snps_obj.snps[backbone][pos][indel_counter] = "-"


					else:
						current_nuc = ref_snps_obj.snps[backbone][pos]
						ref_snps_obj.snps[backbone][pos] = { 0 : current_nuc, indel_counter : "-" } # When indels are found they are numbered from 1 at their position in the ref sequence

				else:
					ref_snps_obj.snps[backbone][pos] = { indel_counter : "-" }

				if pos in query_snps_obj.snps[backbone]:
					
					if isinstance(query_snps_obj.snps[backbone][pos],dict):
						query_snps_obj.snps[backbone][pos][indel_counter] = quernuc
					
					else:
						current_nuc = query_snps_obj.snps[backbone][pos]
						query_snps_obj.snps[backbone][pos] = { 0 : current_nuc, indel_counter : quernuc}

				else:
					query_snps_obj.snps[backbone][pos] = { indel_counter : quernuc }
					

			if quernuc == ".":
				indel_counter = 1
				if pos not in ref_snps_obj.snps[backbone]:
					ref_snps_obj.snps[backbone][pos] = refnuc
				query_snps_obj.snps[backbone][pos] = "-"


	return ref_snps_obj, query_snps_obj



def fasta_to_dict(FASTA_file):
	"""
	Args:
		FASTA_file (str): Entire fasta file as a string.

	
	Returns:
		(dict) dict with the fasta file organized as follows: {contig_name: sequence}.
	"""
	fasta_dict = {}
	fastas = FASTA_file.split(">")
	trimmed_fastas = []
	for i in fastas:
		if len(i) != 0:
			trimmed_fastas.append(i)

	fastas = trimmed_fastas

	for i in fastas:
		header = i.split("\n")[0]
		seq = "".join(i.split("\n")[1:])
		fasta_dict[header] = seq

	return fasta_dict


def fill_query_dict(ref_dict, query_dict):
	"""
	Given a dict with reference genome positions and nucleotides, fills in any missing positions in a query dict with the reference position.
	Expects dicts of format { contig/scaffold : { position : nucleotide , position_with_indel : { 0 : nucleotide , 1 : "-" } } }
	Args:
		ref_dict (dict): dictionary of all the positions of interest in the reference genome.
		query_dict (dict): dictionary of all the positions of interest in the query genome.
	
	Returns:
		(dict) Modified form of the query_dict with any positions found in the reference dict that weren't found in the query dict added in.

	"""

	for backbone, backbone_dict in ref_dict.items():
		if backbone not in query_dict:
			query_dict[backbone] = backbone_dict
		else:
			for position, nucleotide in ref_dict[backbone].items():
				if position not in query_dict[backbone]:
					query_dict[backbone][position] = nucleotide
				elif isinstance(query_dict[backbone][position], dict):
					if isinstance(ref_dict[backbone][position], dict):
						if set(query_dict[backbone][position].keys()) != set(ref_dict[backbone][position].keys()):
							if 0 in ref_dict[backbone][position]:
								if not 0 in query_dict[backbone][position]:
									query_dict[backbone][position][0] = ref_dict[backbone][position][0]
						if len(query_dict[backbone][position]) != len(ref_dict[backbone][position]):
							for i in set(query_dict[backbone][position]).union(set(ref_dict[backbone][position])):
								if i not in query_dict[backbone][position].keys():
									query_dict[backbone][position][i] = "-"
				elif not isinstance(query_dict[backbone][position], dict):
					if isinstance(ref_dict[backbone][position], dict):
						current_nuc = query_dict[backbone][position]
						query_dict[backbone][position] = { 0 : current_nuc }
						for i in range(1,len(ref_dict[backbone][position])):
							query_dict[backbone][position][i] = "-"


	return query_dict




def make_snp_matrix(snps_obj_list,singleton):
	"""
	Flattens all the dictionaries of snps in each snps_object class and adds them to a single subdict associated with their genome ID as a key in the main dict {genome_id : {contig_position : nucleotide}}
	Args:
		snps_obj_list (list): List of snps_object class instances for all the query files in your dataset
	
	Returns:
		(dict) {genome_id : {contig_position : nucleotide}}
	
	"""

	snp_matrix = {"Genome_ID" : []}
	for entry in snps_obj_list:
		snp_matrix[entry.genomeid] = {}
		for backbone, pos_dict in sorted(entry.snps.items()):
			for pos, variant in sorted(pos_dict.items()):
				if not isinstance(variant,dict):
					if entry.genomeid == snps_obj_list[0].genomeid:
						snp_matrix["Genome_ID"].append("%s_position_%i" %(backbone, pos))
					snp_matrix[entry.genomeid]["%s_position_%i" %(backbone, pos)] = variant
				else: 
					for indel_pos, indel in sorted(variant.items()):
						if entry.genomeid == snps_obj_list[0].genomeid:
							snp_matrix["Genome_ID"].append("%s_position_%i_indel_%i" %(backbone, pos, indel_pos))
						snp_matrix[entry.genomeid]["%s_position_%i_indel_%i" %(backbone, pos, indel_pos)] = indel
	if singleton:
		return remove_singletons(snp_matrix)
	else:
		return snp_matrix

def remove_singletons(snp_matrix):
	'''
	Author: Alex P.R. Phillips
	Detects positions in the SNP matrix where only one genome contains a certain base at that position,
	removes that position, prints that information to the buffer, and returns a new matrix without them.
	Args:
		snp_matrix (dict): Dictionary of structure {genome: {position: base}} produced by the function above
	Returns: 
		(dict) {genome_id : {contig_position : nucleotide}}
	'''

	singleton_positions = {}
	for pos in snp_matrix['Genome_ID']:
			seq = ''.join([snp_matrix[genome][pos] for genome in snp_matrix if genome != 'Genome_ID']).upper()
			base_counts = {base: seq.count(base) for base in 'ACGT'}
			if 1 in base_counts.values():
				bases = [x for x in base_counts if base_counts[x] == 1]
				genomes = [x for x in snp_matrix if x != 'Genome_ID' and snp_matrix[x][pos].upper() in bases]
				singleton_positions[pos] = {genome: snp_matrix[genome][pos] for genome in genomes}
				singleton_positions[pos]['counts'] = base_counts
				print('Singleton position ' + pos + ' removed; '  + re.sub("[{}']",'',str(singleton_positions[pos])))
	new_snp_mat = {
		genome:
			{position:
			snp_matrix[genome][position] for position in snp_matrix[genome] if position not in singleton_positions
			}
		for  genome in snp_matrix if genome != 'Genome_ID'}

	new_snp_mat['Genome_ID'] = [x for x in snp_matrix['Genome_ID'] if x not in singleton_positions]
	return new_snp_mat


def make_snp_matrix_multifasta(snps_obj_list):
	"""
	Flattens all the dictionaries of snps in each snps_object class and adds them to a single subdict associated with their genome ID as a key in the main dict {genome_id : {contig : sequence}}
	Args:
		snps_obj_list (list): List of snps_object class instances for all the query files in your dataset
	
	Returns:
		(dict) {genome_id : {contig : sequence}}
	
	"""

	snp_matrix = {}
	for entry in snps_obj_list:
		snp_matrix[entry.genomeid] = defaultdict(str)
		for backbone, pos_dict in sorted(entry.snps.items()):
			for pos, variant in sorted(pos_dict.items()):
				if not isinstance(variant,dict):
					snp_matrix[entry.genomeid][backbone] += variant
				else: 
					for indel_pos, indel in sorted(variant.items()):
						snp_matrix[entry.genomeid][backbone] += indel

	return snp_matrix

def fill_ref_dict_with_seq(ref_snps_obj, ref_seq_dict):
	"""
	If the user wants the whole core genome, this fills any missing positions with the provided reference genome sequence.
	Args:
		ref_snps_obj (snps_object class instance): snps_object representation of the reference genome.
		ref_seq_dict (dict): dict representation of the refence genome fasta file
	
	Returns:
		(snps_object class instance) snps_object representation of the reference genome with invariant sites added.
	"""
	for backbone in ref_seq_dict.keys():
		if backbone not in ref_snps_obj.snps:
			ref_snps_obj.snps[backbone] = {(i+1):s for i, s in enumerate(ref_seq_dict[backbone])}
		else:
			for position, base in enumerate(ref_seq_dict[backbone]):
				if (position + 1) not in ref_snps_obj.snps[backbone]:
					ref_snps_obj.snps[backbone][position+1] = base
	return ref_snps_obj


	

def main():


	parser = argparse.ArgumentParser(
		description="After running spine on a set of genomes to find the core genome and then running nucmer show-snps to identify differences in core genome sequence between genomes, this script converts all the .snps files output by nucmer into a fasta formatted alignment of just the variable sites in each backbone sequences.\
		\n\nExample usage : snps2fasta.py -r Spine/backbone.fasta -f Out/alignment.fasta -whole -m Out/snp_matrix.csv -d '\\t' -p '(.*)_core\.snps' Nucmer/*.snps",
		formatter_class=argparse.RawTextHelpFormatter)
	parser.add_argument(
		"-r",  dest="reference", required = True,
		help="Specify reference backbone fasta file. "
		)
	parser.add_argument(
		"-f", dest="out_fasta", required = False,
		help="Specify output fasta filename."
		)
	parser.add_argument(
		"-m", dest="out_matrix", required = False, 
		help="Specify output matrix filename."
		)
	parser.add_argument(
		"-d", dest="matrix_delim", nargs="?", default = ',',
		help="Specify output matrix delimeter. Default comma delimeted"
		)
	parser.add_argument(
		"-p", dest="filename_regex", nargs="?", default = r'(.+)',
		help="Specify regex pattern to capture genome ID from filename for use as fasta header and rowname in snp matrix. Default behavior is to use the whole filename."
		)
	parser.add_argument(
		"-whole", dest="whole", action='store_true',  
		help="Specify whether you want the output fasta to be the entire core sequence or just the variant sites. "
		)
	parser.add_argument(
		"-remove_singletons", dest="remove_singletons", action='store_true',  
		help="Specify whether you want to remove sites where only one genome contains a different base."
		)
	parser.add_argument(
		"snps_files", nargs="+",  
		help="Specify input core.snps files produced by nucmer. "
		)
	parser.add_argument(
		"-multifasta", dest="multifasta", action='store_true',  
		help="Specify Whether you want the output fasta to be the each aligned core segment in a separate file. With this option you will need to provide an output directory into which one file per core segment will be produced. Each file will contain one fasta sequence per genome corresponding to an aligned core segment. Can be combined with the -whole option to control if you only want variant sites or the whole core genome."
		)
	parser.add_argument(
		"-o", dest="out_dir", required = False,
		help="If you chose the -multifasta option, this option can be used to define the path to the directory you want the multifastas written."
		)




	args = parser.parse_args(sys.argv[1:])

	if not any([args.out_fasta, args.out_matrix, all([args.out_dir, args.multifasta])]):
		print("You did not provide enough output instructions. Use -m to output a snp matrix, -f to output an aligned multifasta of concatenated sequences, or both -o and -multifasta to output aligned multifastas of each individual core segment.")
		sys.exit()
	if any([args.out_dir, args.multifasta]) and not all([args.out_dir, args.multifasta]):
		print("you must provide both -o and -multifasta to output aligned multifastas of each individual core segment.")
		sys.exit()

	if args.multifasta:
		outdir = args.out_dir + '/' if args.out_dir[-1] != '/' else args.out_dir
		if not os.path.isdir(outdir):
			print("Provided output directory does not exist. It will be created.")
			os.makedirs(outdir)


	with open(args.reference, 'r') as inref:
		ref_fasta = fasta_to_dict(inref.read())

	query_snps_list = []
	snp_mat = False

	ref_snps_obj = snps_object("Reference")
	for file in args.snps_files:
		print("Reading in .snps files...")
		print("Processing .snps file %i of %i" %(args.snps_files.index(file)+1, len(args.snps_files)))
		genomeid = re.match(args.filename_regex ,file.split(os.path.sep)[-1])[1]
		ref_snps_obj, query_snps_obj = parse_snps(ref_fasta, ref_snps_obj, file, genomeid)
		query_snps_list.append(query_snps_obj)

	for i in range(len(query_snps_list)):
		print("Adding reference sequence at variant sites not found in .snps file to each entry...")
		print("Processing .snps file %i of %i" %(i+1, len(query_snps_list)))
		query_snps_list[i].snps = fill_query_dict(ref_snps_obj.snps, query_snps_list[i].snps)

	snp_count = 0
	for v in ref_snps_obj.snps.values():
		for subv in v.values():
			if isinstance(subv, dict):
				for subsubv in subv.values():
					snp_count += 1
			else:
				snp_count += 1

	if args.out_matrix:
		print("Building SNP matrix...")

		snp_mat = make_snp_matrix(query_snps_list,args.remove_singletons)

		print("Writing SNP matrix file...")

		# with gzip.open("snp_mat_dict.pkl.gzip", 'wb') as pklout:
		# 	pickle.dump(snp_mat, pklout, protocol=pickle.HIGHEST_PROTOCOL)

		with open(args.out_matrix, 'w+') as outmat:
			headers = list(snp_mat["Genome_ID"])
			for k in sorted(snp_mat.keys()):
				if k == "Genome_ID":
					pass
				else:
					write_string.append(k + args.matrix_delim + args.matrix_delim.join(list(snp_mat[k][i] for i in snp_mat["Genome_ID"])))
			outmat.write('\n'.join(write_string))

	if not args.whole:
		if args.out_fasta:
			if not snp_mat:
				print("Building SNP matrix...")
				snp_mat = make_snp_matrix(query_snps_list,args.remove_singletons)

	else:

		print("Adding reference sequence at invariant sites to each entry...")
		ref_snps_obj = fill_ref_dict_with_seq(ref_snps_obj, ref_fasta)

		for i in range(len(query_snps_list)):
			print("Processing .snps file %i of %i" %(i+1, len(query_snps_list)))
			query_snps_list[i].snps = fill_query_dict(ref_snps_obj.snps, query_snps_list[i].snps)
			query_snps_list[i].snps = {key:{k:v for k,v in sorted(query_snps_list[i].snps[key].items())} for key in sorted(query_snps_list[i].snps)}

		del ref_snps_obj

		print("Building SNP and backbone sequence matrix for whole core genome...")
		snp_mat = make_snp_matrix(query_snps_list,args.remove_singletons)

		if not args.multifasta:
			del query_snps_list

	if args.out_fasta:
		print("Writing fasta file...")

		with open(args.out_fasta, 'w+') as outf:
			fasta_list = []
			ref_genome = re.match(args.filename_regex ,args.snps_files[0].split(os.path.sep)[-1])[1] # The first genome in the dict will be the reference for the purpose of snp order
			for k,v in snp_mat.items():
				if k != "Genome_ID":
					fasta_list.append(">" + k + '\n' + "".join([v[i] for i in snp_mat[ref_genome].keys()]))
			outf.write('\n'.join(fasta_list) + '\n')

	if args.multifasta:
		multifasta_snpmat = make_snp_matrix_multifasta(query_snps_list)
		multifastas_dict = defaultdict(dict) # {contig : {genome_id : sequence}}
		for entry, subdict in multifasta_snpmat.items():
			for contig, sequence in subdict.items():
				multifastas_dict[contig][entry] = sequence
		for contig, contig_dict in multifastas_dict.items():
			with open(outdir + contig + '.fna', 'w') as fout:
				fout.write("".join([">{}\n{}\n".format(k,v) for k,v in contig_dict.items()]))


	stop = time.time()

	print("All done! Found a total of %i variant sites among %i genomes in %.3f seconds." %(snp_count, len(args.snps_files), stop-start))

if __name__ == "__main__":
	main()
