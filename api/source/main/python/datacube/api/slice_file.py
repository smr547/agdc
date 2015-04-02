#!/bin/env python
"""
Slice a file into N subfiles, if file is a CSV then repeat the header
"""
import os
import math
import argparse

if __name__=="__main__":

    parser = argparse.ArgumentParser(description="Slice a file into N subfiles like myfile_slice_999.csv")
    parser.add_argument("-n", "--slices", help="number of subfiles", \
        type=int, required=True)
    parser.add_argument("-f", "--file", help="path to input file", \
        type=str, required=True)
    parser.add_argument("-o", "--output", help="path to output directory", \
        type=str, default=".")
    parser.add_argument("-s", "--suffix", help="suffix to place on slice files (default=none)", \
        type=str, default="")
    parser.add_argument("-p", "--prefix", help="prefix to place on slice files (default=original filename)", \
        type=str, default="")
    parser.add_argument("-r", "--repeat_header", help="repeat first line as CSV header", \
        action="store_false")
    args = parser.parse_args()

    file_count = args.slices

    line_count = 0
    header = None
    with open(args.file,"r") as in_file:
         if args.repeat_header:
             header = in_file.readline()
         for line in in_file:
             line_count += 1

    # compute lines per slice file

    lines_per_file = int(math.ceil(line_count / (file_count * 1.0)))

    # rewind input file and start slicing

    with open(args.file,"r") as in_file:
         if args.repeat_header:
             header = in_file.readline()
         for file_no in range(1, file_count+1):
             file_name = "out_%d.csv" % file_no
             out_file = open(file_name, "w")
             if args.repeat_header:
                 out_file.write(header)
             for i in range(0, lines_per_file):
                 line = in_file.readline()
                 if line is None:
                     break
                 out_file.write(line)
             out_file.close()
