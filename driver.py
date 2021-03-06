#!/usr/bin/env python
import argparse
import json
import warnings
import math

import ROOT
ROOT.gROOT.SetBatch(True)
ROOT.PyConfig.IgnoreCommandLineOptions = True
ROOT.PyConfig.DisableRootLogon = True


def setup_samplelist(args):
    with open(args.sample) as fin:
        samples_in = json.load(fin)

    if args.split is not None:
        # Split the filelist into even chunks
        njob, ijob = args.split
        all_files = sum((info['files'] for info in samples_in.values()), [])
        files_per_job = math.ceil(len(all_files) / njob)  # ! Assumes python 3 true division
        files_this_job = all_files[ijob*files_per_job:(ijob+1)*files_per_job]
        samples = {}
        for sample, info in samples_in.items():
            files = [f for f in info.pop('files') if f in files_this_job]
            if len(files) == 0:
                continue
            info['files'] = files
            samples[sample] = info
    else:
        samples = samples_in

    return samples


def setup_selector(args, selector, dataset, info):
    inputs = ROOT.TList()
    selector.SetInputList(inputs)

    # We can send any object inheiriting from TObject into the selector
    # A corresponding receive function has to be implemented in TSelector::Begin()
    fin = ROOT.TFile.Open("corrections/electron_scalefactors.root")
    electronSF = fin.Get("scalefactors_Tight_Electron")
    electronSF.SetDirectory(0)  # Prevent cleanup when file closed
    inputs.Add(electronSF)

    # We can also simply modify any public members of the selector from python
    selector.isRealData_ = False

    fin = ROOT.TFile.Open("corrections/muon_scalefactors.root")
    muonSF = fin.Get("scalefactors_Iso_MuonTightId")
    muonSF.SetDirectory(0)
    selector.muCorr_ = muonSF

    fin = ROOT.TFile.Open("corrections/pileup_scalefactors.root")
    # Suppose we are looking at the buggy 2017 MC and need per-dataset pileup SF
    pileupSF = fin.Get(dataset)
    if pileupSF != None:
        pileupSF.SetDirectory(0)
        selector.puCorr_ = pileupSF
    else:
        selector.puCorr_ = None


def run(args):
    ROOT.gROOT.ProcessLine(".L {}.C+".format(args.selector))
    warnings.filterwarnings(action='ignore', category=RuntimeWarning, message='no dictionary for class')
    SelectorType = getattr(ROOT, args.selector)

    outputFile = ROOT.TFile(args.output, "recreate")

    samples = setup_samplelist(args)
    for dataset, info in samples.items():
        print(f"Processing {dataset}")
        filelist = info['files']
        if args.limit is not None:
            filelist = filelist[:args.limit]

        selector = SelectorType()
        setup_selector(args, selector, dataset, info)

        for filename in filelist:
            file = ROOT.TFile.Open(filename)
            tree = file.Get("Events")
            if args.maxevents:
                tree.Process(selector, "", args.maxevents)
            else:
                tree.Process(selector)

        outputDir = outputFile.mkdir(dataset)
        ROOT.SetOwnership(outputDir, False)
        outputDir.cd()
        for item in selector.GetOutputList():
            item.Write()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run NanoSelector')
    parser.add_argument('--selector', default='NanoSelector', help='The name of the selector to use (default: %(default)s)')
    parser.add_argument('--limit', type=int, default=None, metavar='N', help='Limit to the first N files of each dataset in sample JSON')
    parser.add_argument('--maxevents', type=int, default=None, metavar='N', help='Limit to the first N entries of the tree in each file')
    parser.add_argument('--sample', default='datadef_nano.json', help='Input sample list json (default: %(default)s)')
    parser.add_argument('--output', default='output.root', help='Output filename (default: %(default)s)')
    parser.add_argument('--split', type=int, help="Split input file list and process subsection. IJOB is zero-indexed", nargs=2, metavar=('NJOBS', 'IJOB'))
    args = parser.parse_args()

    run(args)
