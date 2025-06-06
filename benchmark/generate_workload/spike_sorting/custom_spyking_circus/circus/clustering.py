from circus.shared.utils import *
import circus.shared.files as io
import circus.shared.algorithms as algo
from circus.shared import plot
import warnings
import scipy
import scipy.optimize
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=FutureWarning)
    import h5py
from circus.shared.probes import get_nodes_and_edges, get_nodes_and_positions
from circus.shared.files import get_dead_times
from circus.shared.messages import print_and_log, init_logging
from circus.shared.utils import get_parallel_hdf5_flag
from circus.shared.mpi import detect_memory
import scipy
import scipy.optimize

def main(params, nb_cpu, nb_gpu, use_gpu):

    parallel_hdf5 = get_parallel_hdf5_flag(params)
    _ = init_logging(params.logfile)
    logger = logging.getLogger('circus.clustering')
    #################################################################
    data_file = params.data_file
    n_e = params.getint('data', 'N_e')
    n_total = params.nb_channels
    n_t = params.getint('detection', 'N_t')
    SHARED_MEMORY = get_shared_memory_flag(params)
    dist_peaks = params.getint('detection', 'dist_peaks')
    template_shift = params.getint('detection', 'template_shift')
    file_out_suff = params.get('data', 'file_out_suff')
    sign_peaks = params.get('detection', 'peaks')
    alignment = params.getboolean('detection', 'alignment')
    isolation = params.getboolean('detection', 'isolation')
    over_factor = float(params.getint('detection', 'oversampling_factor'))
    nb_jitter = params.getint('detection', 'nb_jitter')
    matched_filter = params.getboolean('detection', 'matched-filter')
    use_barycenter = params.getboolean('detection', 'use_barycenter')
    _ = params.getfloat('detection', 'spike_thresh')
    spike_width = params.getfloat('detection', 'spike_width')
    noise_thresh = params.getfloat('clustering', 'noise_thr')
    if params.getboolean('data', 'global_tmp'):
        tmp_path_loc = os.path.join(os.path.abspath(params.get('data', 'file_out_suff')), 'tmp')
    else:
        tmp_path_loc = tempfile.gettempdir()

    plot_path = os.path.join(params.get('data', 'file_out_suff'), 'plots')
    do_temporal_whitening = params.getboolean('whitening', 'temporal')
    do_spatial_whitening = params.getboolean('whitening', 'spatial')
    safety_time = params.getint('clustering', 'safety_time')
    safety_space = params.getboolean('clustering', 'safety_space')
    comp_templates = params.getboolean('clustering', 'compress')
    dispersion = params.get('clustering', 'dispersion').replace('(', '').replace(')', '').split(',')
    dispersion = [float(v) for v in dispersion]
    nodes, edges = get_nodes_and_edges(params)
    _, positions = get_nodes_and_positions(params)
    chunk_size = detect_memory(params)
    max_elts_elec = params.getint('clustering', 'max_elts')
    two_components = params.getboolean('clustering', 'two_components')
    if sign_peaks == 'both':
        max_elts_elec *= 2
    nb_elts = int(params.getfloat('clustering', 'nb_elts') * n_e * max_elts_elec)
    nb_repeats = params.getint('clustering', 'nb_repeats')
    make_plots = params.get('clustering', 'make_plots')
    debug_plots = params.get('clustering', 'debug_plots')
    halo_rejection = params.getfloat('clustering', 'halo_rejection')
    merging_param = params.getfloat('clustering', 'merging_param')
    merging_method = params.get('clustering', 'merging_method')
    sparsity_limit = params.getfloat('clustering', 'sparsity_limit')
    remove_mixture = params.getboolean('clustering', 'remove_mixture')
    extraction = params.get('clustering', 'extraction')
    smart_search = params.getboolean('clustering', 'smart_search')
    n_abs_min = params.getint('clustering', 'n_abs_min')
    sensitivity = params.getfloat('clustering', 'sensitivity')
    hdf5_compress = params.getboolean('data', 'hdf5_compress')
    blosc_compress = params.getboolean('data', 'blosc_compress')
    test_clusters = params.getboolean('clustering', 'test_clusters')
    bad_clusters_ratio = params.getint('clustering', 'bad_clusters_ratio')
    fine_amplitude = params.getboolean('clustering', 'fine_amplitude')
    sparsify = params.getfloat('clustering', 'sparsify')
    ss_scale = params.getfloat('clustering', 'smart_search_scale')
    debug = params.getboolean('clustering', 'debug')
    tmp_limits = params.get('fitting', 'amp_limits').replace('(', '').replace(')', '').split(',')
    _ = list(map(float, tmp_limits))
    elt_count = 0
    m_ratio = params.getfloat('clustering', 'm_ratio')
    sub_output_dim = params.getint('clustering', 'sub_dim')
    inv_nodes = numpy.zeros(n_total, dtype=numpy.int32)
    inv_nodes[nodes] = numpy.arange(len(nodes))
    to_write = ['clusters_', 'times_', 'data_', 'peaks_', 'noise_times_']
    if debug:
        to_write += ['rho_', 'delta_']
    ignore_dead_times = params.getboolean('triggers', 'ignore_times')
    jitter_range = params.getint('detection', 'jitter_range')
    template_shift_2 = template_shift + jitter_range
    nb_ss_bins = params.get('clustering', 'nb_ss_bins')
    if nb_ss_bins != 'auto':
        nb_ss_bins = int(nb_ss_bins)
    max_nb_rand_ss = params.getint('clustering', 'nb_ss_rand')
    nb_snippets = params.getint('clustering', 'nb_snippets')
    ignored_mixtures = params.getfloat('clustering', 'ignored_mixtures')
    use_hanning = params.getboolean('detection', 'hanning')
    use_savgol = params.getboolean('clustering', 'savgol')
    templates_normalization = params.getboolean('clustering', 'templates_normalization')
    rejection_threshold = params.getfloat('detection', 'rejection_threshold')
    smoothing_factor = params.getfloat('detection', 'smoothing_factor')
    noise_window = params.getint('detection', 'noise_time')
    low_channels_thr = params.getint('detection', 'low_channels_thr')
    fixed_amplitudes = params.getboolean('clustering', 'fixed_amplitudes')

    sparsify_radius = params.getfloat('clustering', 'radius')
    radius_en = params.getboolean('clustering', 'radius_en')
    print("radius_en", radius_en)
    print("sparsify_radius", sparsify_radius)

    # Comment:
    # weird threshold is used to remove abnormal behavior (Default: Not used)
    weird_thresh = params.get('detection', 'weird_thresh')
    if weird_thresh != '':
        ignore_artefacts = True
        weird_thresh = io.load_data(params, 'weird-thresholds')
    else:
        ignore_artefacts = False

    if not fixed_amplitudes:
        nb_amp_bins = params.getint('clustering', 'nb_amp_bins')
        splits = np.linspace(0, params.data_file.duration, nb_amp_bins)
        # in between the amp bin
        interpolated_times = np.zeros(len(splits) - 1, dtype=numpy.float32)
        for count in range(0, len(splits) - 1):
            interpolated_times[count] = (splits[count] + splits[count + 1])/2

        # add zero and end
        interpolated_times = numpy.concatenate(([0], interpolated_times, [params.data_file.duration]))
        nb_amp_times = len(splits) + 1

    data_file.open()
    #################################################################

    mads = io.load_data(params, 'mads')
    stds = io.load_data(params, 'stds')

    if rejection_threshold > 0:
        reject_noise = True
        noise_levels = stds * (2 * noise_window + 1)
    else:
        reject_noise = False

    if sign_peaks == 'negative':
        search_peaks = ['neg']
    elif sign_peaks == 'positive':
        search_peaks = ['pos']
    elif sign_peaks == 'both':
        search_peaks = ['neg', 'pos']
    else:
        raise ValueError("unexpected value: %s" % sign_peaks)

    nodes_indices = {}
    for elec in numpy.arange(n_e):
        # nodes_indices => all the nearby node ids for the given electrode id
        nodes_indices[elec] = inv_nodes[edges[nodes[elec]]]

    print("positions", positions)
    # [[x, y, z], ... ]

    # Comment
    # smart: a smarter way to sample subset of the spikes for clustering
    # (we do not cluster all the spikes)
    smart_searches = {}
    for p in search_peaks:
        smart_searches[p] = numpy.ones(n_e, dtype=numpy.float32) * int(smart_search)

    basis = {}

    # Comment:
    # there are three types of filters
    # 1) hanning filter => for detection
    # 2) savgol => template smoothing
    # 3) alignment
    # The three procedures are not applied in the fitting phase
    # Required only in the clustering procedure
    if use_hanning:
        hanning_filter = numpy.hanning(n_t)[:, numpy.newaxis]
    else:
        hanning_filter = None

    if use_savgol:
        from scipy.ndimage import gaussian_filter1d
        savgol_window = params.getint('clustering', 'savgol_window')
        centered_filter = numpy.zeros(n_t)
        centered_filter[template_shift - savgol_window:template_shift+savgol_window] = 1
        centered_filter = gaussian_filter1d(centered_filter, savgol_window)
        centered_filter /= centered_filter.max()
    else:
        savgol_filter = None
        savgol_window = None

    # align and smooth the data to generate the representative waveform
    if alignment:
        cdata = numpy.linspace(-jitter_range, jitter_range, nb_jitter)
        xdata = numpy.arange(-template_shift_2, template_shift_2 + 1)
        xoff = len(cdata) / 2.0
        duration = template_shift_2
        m_size = (2 * template_shift_2 + 1)
        align_factor = m_size
        local_factors = align_factor*((smoothing_factor*mads)**2)
    else:
        cdata = None  # default assignment (for PyCharm code inspection)
        xdata = None  # default assignment (for PyCharm code inspection)
        xoff = None  # default assignment (for PyCharm code inspection)
        duration = template_shift
        align_factor = None  # default assignment (for PyCharm code inspection)

    if sign_peaks in ['negative', 'both']:
        basis['proj_neg'], basis['rec_neg'] = io.load_data(params, 'basis')
    if sign_peaks in ['positive', 'both']:
        basis['proj_pos'], basis['rec_pos'] = io.load_data(params, 'basis-pos')

    # Comment:
    # the threshold and filter (both spatial and temporal) for the peak detection (for each electrode)
    # predetermined in the whitenning phase
    thresholds = io.load_data(params, 'thresholds')
    n_scalar = n_e * n_t
    if do_spatial_whitening:
        spatial_whitening = io.load_data(params, 'spatial_whitening')
    else:
        spatial_whitening = None
    if do_temporal_whitening:
        temporal_whitening = io.load_data(params, 'temporal_whitening')
    else:
        temporal_whitening = None

    # Comment:
    # These values required for the matched-filtering only (Default: False)
    waveform_neg = numpy.empty(0)
    matched_thresholds_neg = numpy.empty(0)
    waveform_pos = numpy.empty(0)
    matched_thresholds_pos = numpy.empty(0)
    if matched_filter:
        if sign_peaks in ['negative', 'both']:
            waveform_neg = io.load_data(params, 'waveform')[::-1]
            waveform_neg /= (numpy.abs(numpy.sum(waveform_neg)) * len(waveform_neg))
            matched_thresholds_neg = io.load_data(params, 'matched-thresholds')
        if sign_peaks in ['positive', 'both']:
            waveform_pos = io.load_data(params, 'waveform-pos')[::-1]
            waveform_pos /= (numpy.abs(numpy.sum(waveform_pos)) * len(waveform_pos))
            matched_thresholds_pos = io.load_data(params, 'matched-thresholds-pos')

    if ignore_dead_times:
        if SHARED_MEMORY:
            all_dead_times, mpi_memory_3 = get_dead_times(params)
        else:
            all_dead_times = get_dead_times(params)
    else:
        all_dead_times = None

    result = {}

    if use_gpu:
        import cudamat as cmt
        # Need to properly handle multi GPU per MPI nodes?
        if nb_gpu > nb_cpu:
            gpu_id = int(comm.rank // nb_cpu)
        else:
            gpu_id = 0
        cmt.cuda_set_device(gpu_id)
        cmt.init()
        cmt.cuda_sync_threads()

    # Comment:
    # test clusters is set to False as Default
    if test_clusters:
        injected_spikes = io.load_data(params, 'injected_spikes')
    else:
        injected_spikes = None  # default assignment

    if comm.rank == 0:
        if not os.path.exists(tmp_path_loc):
            os.makedirs(tmp_path_loc)

    comm.Barrier()

    if use_gpu and do_spatial_whitening:
        spatial_whitening = cmt.CUDAMatrix(spatial_whitening, copy_on_host=False)

    elec_positions = {}
    elec_positions_shanks = {}
    elec_ydata = {}

    # per electrode results
    for i in range(n_e):
        result['all_times_' + str(i)] = numpy.zeros(0, dtype=numpy.uint32)
        result['times_' + str(i)] = numpy.zeros(0, dtype=numpy.uint32)
        result['clusters_' + str(i)] = numpy.zeros(0, dtype=numpy.int32)
        result['peaks_' + str(i)] = [numpy.empty(0, dtype=numpy.uint32)]
        result['noise_times_' + str(i)] = [numpy.zeros(0, dtype=numpy.uint32)]
        # contains different pca for different peak type
        for p in search_peaks:
            result['pca_%s_' % p + str(i)] = None
        indices = nodes_indices[i]
        elec_positions[i] = numpy.where(indices == i)[0]
        elec_ydata[i] = numpy.arange(len(indices))

        shank_nodes, _ = get_nodes_and_edges(params, shank_with=nodes[i])
        indices = inv_nodes[shank_nodes]
        elec_positions_shanks[i] = numpy.where(indices == i)[0]

    max_elts_elec //= comm.size
    nb_elts //= comm.size
    few_elts = False
    nb_chunks, _ = data_file.analyze(chunk_size)

    if nb_chunks < comm.size:

        res = io.data_stats(params, show=False)
        chunk_size = int(res*params.rate//comm.size)
        if comm.rank == 0:
            print_and_log(["Too much cores, automatically resizing the data chunks"], 'debug', logger)

        nb_chunks, last_chunk_len = data_file.analyze(chunk_size)

    if smart_search is False:
        gpass = 1
    else:
        gpass = 0

    # We will perform several passes to enhance the quality of the clustering
    sdata = None
    loop_max_elts_elec = None
    loop_nb_elts = None
    local_nb_clusters = 0
    # local_hits = 0
    local_mergings = 0
    cluster_results = {}

    # I guess this is more relevant, to take signals from all over the recordings
    numpy.random.seed(42)
    all_chunks = numpy.random.permutation(numpy.arange(nb_chunks, dtype=numpy.int64))

    #numpy.random.seed(0)
    numpy.random.seed(comm.rank)
    # the number of passes for clustering (to improve the quality of the clustering)
    # @gpass == 0 -> perform smart selection
    while gpass < (nb_repeats + 1):
        comm.Barrier()
        if gpass == 1:
            for p in search_peaks:

                # all_gather_array -> MPI protocol
                smart_searches[p] = all_gather_array(smart_searches[p][comm.rank::comm.size], comm, 0).astype(numpy.bool_)
                indices = []
                for idx in range(comm.size):
                    indices += list(numpy.arange(idx, n_e, comm.size))
                indices = numpy.argsort(indices)
                smart_searches[p] = smart_searches[p][indices]

                if numpy.any(smart_searches[p] == 1):
                    max_nb_rand_ss *= len(numpy.where(smart_searches[p] == 1)[0])
                    random_numbers = numpy.random.rand(max_nb_rand_ss)
                    random_count = 0
                    continue

            if search_peaks == ['neg']:
                sdata = smart_searches[p]
            elif search_peaks == ['pos']:
                sdata = smart_searches['pos']
            elif search_peaks == ['neg', 'pos']:
                sdata = numpy.logical_or(smart_searches['pos'], smart_searches['neg'])

        if comm.rank == 0:
            if gpass == 0:
                if isolation:
                    print_and_log(["Searching isolated random spikes to sample amplitudes..."], 'default', logger)
                else:
                    print_and_log(["Searching random spikes to sample amplitudes..."], 'default', logger)
            elif gpass == 1:
                # if the smart search is disables -> all the sdata will be 0
                if not numpy.all(sdata > 0):
                    lines = ["Smart Search disabled on %d electrodes" % (numpy.sum(sdata == 0))]
                    print_and_log(lines, 'debug', logger)
                if numpy.any(sdata > 0):
                    if isolation:
                        lines = [
                            "Smart Search of good isolated spikes for the clustering (%d/%d)..." % (gpass, nb_repeats)
                        ]
                        print_and_log(lines, 'default', logger)
                    else:
                        lines = ["Smart Search of good spikes for the clustering (%d/%d)..." % (gpass, nb_repeats)]
                        print_and_log(lines, 'default', logger)
                else:
                    lines = [
                        "Searching random spikes for the clustering (%d/%d) (no smart search)" % (gpass, nb_repeats)
                    ]
                    print_and_log(lines, 'default', logger)
            else:
                lines = ["Searching random spikes to refine the clustering (%d/%d)..." % (gpass, nb_repeats)]
                print_and_log(lines, 'default', logger)

        for i in range(n_e):

            if gpass == 0:
                for p in search_peaks:
                    result['tmp_%s_' % p + str(i)] = [numpy.zeros(0, dtype=numpy.float32)]
                    result['nb_chunks_%s_' % p + str(i)] = numpy.zeros(1, dtype=numpy.int32)
                    result['count_%s_' % p + str(i)] = 0
                    result['hist_%s_' % p + str(i)] = numpy.zeros(0, dtype=numpy.float32)
                    # the bounds
                    result['bounds_%s_' % p + str(i)] = numpy.zeros(2, dtype=numpy.float32)
                    result['nb_ss_bins_%s_' % p + str(i)] = numpy.zeros(1, dtype=numpy.int32)

            if gpass == 1:
                n_neighb = len(edges[nodes[i]])
                for p in search_peaks:
                    # Comment:
                    # result['dataXXX] stores the whitening PCA results for all the nearby electrodes (within the radius including itself)
                    result['data_%s_' % p + str(i)] = [
                        numpy.zeros((0, basis['proj_%s' % p].shape[1] * n_neighb), dtype=numpy.float32)
                    ]
                    result['count_%s_' % p + str(i)] = 0

                    if smart_search:
                        result['hist_%s_' % p + str(i)] = \
                            comm.bcast(result['hist_%s_' % p + str(i)], root=numpy.mod(i, comm.size))
                        result['bounds_%s_' % p + str(i)] = \
                            comm.bcast(result['bounds_%s_' % p + str(i)], root=numpy.mod(i, comm.size))
                        result['nb_ss_bins_%s_' % p + str(i)] = \
                            comm.bcast(result['nb_ss_bins_%s_' % p + str(i)], root=numpy.mod(i, comm.size))

                    if smart_searches[p][i]:
                        result['bin_size_%s_' % p + str(i)] = \
                            result['bounds_%s_' % p + str(i)][2] - result['bounds_%s_' % p + str(i)][1]

            if gpass == 2:
                for p in search_peaks:
                    # Comment:
                    # stores the coefficients for the clustering PCA
                    result['pca_%s_' % p + str(i)] = \
                        comm.bcast(result['pca_%s_' % p + str(i)], root=numpy.mod(i, comm.size))

            if gpass > 1:
                for p in search_peaks:
                    result['tmp_%s_' % p + str(i)] = [
                        numpy.zeros((0, result['pca_%s_' % p + str(i)].shape[1]), dtype=numpy.float32)
                    ]
                    result['count_%s_' % p + str(i)] = 0

                result['all_times_' + str(i)] = numpy.append(result['all_times_' + str(i)],
                    all_gather_array(
                        result['loc_times_' + str(i)], comm, dtype='uint32', compress=blosc_compress
                    )
                )

            result['loc_times_' + str(i)] = [numpy.zeros(0, dtype=numpy.uint32)]

        # This is not easy to read, but during the smart search pass,
        # we need to loop over all chunks, and every nodes
        # should search spikes for a subset of electrodes, to avoid too many communications.
        if gpass == 0 or not smart_search:
            loop_max_elts_elec = max_elts_elec
            loop_nb_elts = nb_elts
        elif gpass == 1:
            if elt_count < loop_nb_elts - 1:
                lines = [
                    "Node %d found not enough spikes: searching only %d spikes instead of %d"
                    % (comm.rank, elt_count, loop_nb_elts)
                ]
                print_and_log(lines, 'debug', logger)
                loop_nb_elts = elt_count
        else:
            loop_max_elts_elec = max_elts_elec
            loop_nb_elts = nb_elts

        to_explore = list(range(comm.rank, nb_chunks, comm.size))

        local_nb_chunks = len(to_explore)
        rejected = 0
        elt_count = 0
        nb_noise = 0

        if comm.rank == 0:
            to_explore = get_tqdm_progressbar(params, to_explore)

        comm.Barrier()

        for gcount, gidx in enumerate(to_explore):
            gidx = all_chunks[gidx]
            is_first = data_file.is_first_chunk(gidx, nb_chunks)
            is_last = data_file.is_last_chunk(gidx, nb_chunks)

            if not (is_first and is_last):
                if is_last:
                    padding = (-duration, 0)
                elif is_first:
                    padding = (0, duration)
                else:
                    padding = (-duration, duration)
            else:
                padding = (0, 0)

            # if the current iteration spike count is within the boundary
            if elt_count < loop_nb_elts:
                # print "Node", comm.rank, "is analyzing chunk", gidx, "/", nb_chunks, " ..."
                local_chunk, t_offset = data_file.get_data(gidx, chunk_size, padding, nodes=nodes)
                local_shape = len(local_chunk)
                if do_spatial_whitening:
                    if use_gpu:
                        local_chunk = cmt.CUDAMatrix(local_chunk, copy_on_host=False)
                        local_chunk = local_chunk.dot(spatial_whitening).asarray()
                    else:
                        local_chunk = numpy.dot(local_chunk, spatial_whitening)
                if do_temporal_whitening:
                    local_chunk = scipy.ndimage.filters.convolve1d(
                        local_chunk, temporal_whitening, axis=0, mode='constant'
                    )
                #bit_prec = 5
                #range_data = 2 ** (bit_prec - 1)
                #local_chunk = np.round(local_chunk, 0)
                #local_chunk[local_chunk > range_data] = range_data
                #local_chunk[local_chunk < -range_data] = -range_data
                #local_chunk = local_chunk.astype(int)
                #local_chunk = local_chunk.astype(float)

                # How to 

                # Extracting the peaks.
                found_peaktimes = []

                # print "Removing the useless borders..."
                local_borders = (duration, local_shape - duration)

                if ignore_dead_times:
                    dead_indices = numpy.searchsorted(all_dead_times, [t_offset, t_offset + local_shape])

                # Comment:
                # the matched_filter is set to false in default
                if matched_filter:

                    if sign_peaks in ['positive', 'both']:
                        filter_chunk = scipy.ndimage.filters.convolve1d(
                            local_chunk, waveform_pos, axis=0, mode='constant'
                        )
                        for i in range(n_e):
                            # identify peaks using the threshold
                            peaktimes = scipy.signal.find_peaks(
                                filter_chunk[:, i], height=matched_thresholds_pos[i],
                                width=spike_width, distance=dist_peaks, wlen=n_t
                            )[0]
                            peaktimes = peaktimes.astype(numpy.uint32)

                            if ignore_artefacts:
                                artetimes = scipy.signal.find_peaks(numpy.abs(filter_chunk[:, i]), height=weird_thresh[i], width=spike_width, distance=dist_peaks, wlen=n_t)[0]
                                to_keep = numpy.logical_not(numpy.in1d(peaktimes, artetimes))
                                peaktimes = peaktimes[to_keep]

                            idx = (peaktimes >= local_borders[0]) & (peaktimes < local_borders[1])
                            found_peaktimes.append(peaktimes[idx])

                            peaktimes = peaktimes[idx]

                            if ignore_dead_times:
                                if dead_indices[0] != dead_indices[1]:
                                    is_included = numpy.in1d(
                                        peaktimes + t_offset,
                                        all_dead_times[dead_indices[0]:dead_indices[1]]
                                    )
                                    peaktimes = peaktimes[~is_included]

                    if sign_peaks in ['negative', 'both']:
                        filter_chunk = scipy.ndimage.filters.convolve1d(
                            local_chunk, waveform_neg, axis=0, mode='constant'
                        )
                        for i in range(n_e):
                            peaktimes = scipy.signal.find_peaks(
                                filter_chunk[:, i], height=matched_thresholds_neg[i],
                                width=spike_width, distance=dist_peaks, wlen=n_t
                            )[0]
                            peaktimes = peaktimes.astype(numpy.uint32)

                            if ignore_artefacts:
                                artetimes = scipy.signal.find_peaks(numy.abs(filter_chunk[:, i]), height=weird_thresh[i], width=spike_width, distance=dist_peaks, wlen=n_t)[0]
                                to_keep = numpy.logical_not(numpy.in1d(peaktimes, artetimes))
                                peaktimes = peaktimes[to_keep]

                            idx = (peaktimes >= local_borders[0]) & (peaktimes < local_borders[1])
                            peaktimes = peaktimes[idx]

                            if ignore_dead_times:
                                if dead_indices[0] != dead_indices[1]:
                                    is_included = numpy.in1d(
                                        peaktimes + t_offset,
                                        all_dead_times[dead_indices[0]:dead_indices[1]]
                                    )
                                    peaktimes = peaktimes[~is_included]

                            if sign_peaks == 'both':
                                found_peaktimes[-1] = numpy.concatenate((found_peaktimes[-1], peaktimes))
                            else:
                                found_peaktimes.append(peaktimes)

                # Comment:
                # This is a typical thresholding procedure
                else:
                    # iterate over the electrodes
                    for i in range(n_e):
                        x = local_chunk[:, i]
                        height = thresholds[i]
                        if sign_peaks == 'negative':
                            peaktimes = scipy.signal.find_peaks(
                                -x, height=height, width=spike_width, distance=dist_peaks, wlen=n_t
                            )[0]
                        elif sign_peaks == 'positive':
                            peaktimes = scipy.signal.find_peaks(
                                +x, height=height, width=spike_width, distance=dist_peaks, wlen=n_t
                            )[0]
                        elif sign_peaks == 'both':
                            peaktimes = scipy.signal.find_peaks(
                                numpy.abs(x), height=height, width=spike_width, distance=dist_peaks, wlen=n_t
                            )[0]
                        else:
                            peaktimes = numpy.empty(0, dtype=numpy.uint32)
                        peaktimes = peaktimes.astype(numpy.uint32) # return list of local maxima spike times

                        # This is also set to False as default
                        if ignore_artefacts:
                            # it seems that it is removing signals with abnormal behavior
                            artetimes = scipy.signal.find_peaks(numpy.abs(x), height=weird_thresh[i], width=spike_width, distance=dist_peaks, wlen=n_t)[0]
                            to_keep = numpy.logical_not(numpy.in1d(peaktimes, artetimes))
                            peaktimes = peaktimes[to_keep]

                        idx = (peaktimes >= local_borders[0]) & (peaktimes < local_borders[1])
                        peaktimes = peaktimes[idx]

                        if ignore_dead_times:
                            if dead_indices[0] != dead_indices[1]:
                                is_included = numpy.in1d(
                                    peaktimes + t_offset,
                                    all_dead_times[dead_indices[0]:dead_indices[1]]
                                )
                                peaktimes = peaktimes[~is_included]

                        found_peaktimes.append(peaktimes)

                all_peaktimes = numpy.concatenate(found_peaktimes)  # i.e. concatenate once for efficiency

                # Comment:
                # retrieve the peak times for the treshold over all the electrodes
                local_peaktimes, local_indices = numpy.unique(all_peaktimes, return_inverse=True)
                local_offset = t_offset + padding[0]

                if gpass == 0:
                    for i in range(n_e):
                        for p in search_peaks:
                            if result['count_%s_' % p + str(i)] < loop_max_elts_elec:
                                result['nb_chunks_%s_' % p + str(i)] += 1

                if len(local_peaktimes) > 0:
                    # Comment:
                    # the total time interval between the first and the last peak
                    diff_times = local_peaktimes[-1] - local_peaktimes[0]
                    all_times = numpy.zeros((n_e, diff_times+1), dtype=numpy.bool_)
                    padded_peaks = (local_peaktimes - local_peaktimes[0]).astype(numpy.int32)

                    # safety time to separate
                    min_times = numpy.maximum(padded_peaks - safety_time, 0)
                    max_times = numpy.minimum(padded_peaks + safety_time + 1, diff_times + 1)

                    test_extremas = numpy.zeros((n_e, diff_times+1), dtype=numpy.bool_)
                    for i in range(n_e):
                        test_extremas[i, found_peaktimes[i] - local_peaktimes[0]] = True

                    n_times = len(all_peaktimes)
                    shuffling = numpy.random.permutation(numpy.arange(n_times))
                    all_idx = numpy.take(all_peaktimes, shuffling)
                    argmax_peak = local_indices[shuffling]

                    if gpass > 1:
                        for elec in range(n_e):
                            subset = (result['all_times_' + str(elec)] - local_offset).astype(numpy.int32)
                            peaks = numpy.compress((subset >= 0) & (subset < local_shape), subset)
                            inter = numpy.in1d(local_peaktimes, peaks)
                            indices = nodes_indices[elec]
                            remove = numpy.where(inter)[0]
                            for t in remove:
                                if safety_space:
                                    all_times[indices, min_times[t]:max_times[t]] = True
                                else:
                                    all_times[elec, min_times[t]:max_times[t]] = True

                    # print "Selection of the peaks with spatio-temporal masks..."
                    for midx, peak in zip(argmax_peak, all_idx):

                        if elt_count == loop_nb_elts:
                            break

                        is_isolated = True
                        to_accept = False
                        max_test = True

                        # Comment:
                        # The peak time and correponding peaking electrodes
                        # consider temporal overlapping?
                        #print("numpy.where :", numpy.where(test_extremas[:,peak - local_peaktimes[0]]))
                        all_elecs = numpy.where(test_extremas[:, peak - local_peaktimes[0]])[0]
                        data = local_chunk[peak, all_elecs]
                        # data : at some peak, voltage value of all elecs that spike

                        #print("data", data)

                        #print("all elecs :", all_elecs)

                        negative_peak = None
                        loc_peak = None
                        # Comment:
                        # Identify the electrodes with the largest peak
                        # use_barycenter = True by default?
                        if sign_peaks == 'negative':
                            if n_e > 1:
                                if use_barycenter:
                                    weighed_position = data[:, numpy.newaxis] * positions[all_elecs]
                                    barycenter = weighed_position.sum(0)/data.sum()
                                    elec = numpy.argmin(numpy.linalg.norm(barycenter - positions[all_elecs], axis=1))
                                else:
                                    elec = numpy.argmin(data) # pick the electrode with minimum(maximum) peak
                            else:
                                elec = 0
                            negative_peak = True
                            loc_peak = 'neg'
                        elif sign_peaks == 'positive':
                            if n_e > 1:
                                if use_barycenter:
                                    weighed_position = data[:, numpy.newaxis] * positions[all_elecs]
                                    barycenter = weighed_position.sum(0)/data.sum()
                                    elec = numpy.argmin(numpy.linalg.norm(barycenter - positions[all_elecs], axis=1))
                                else:
                                    elec = numpy.argmax(data)
                            else:
                                elec = 0
                            negative_peak = False
                            loc_peak = 'pos'
                        elif sign_peaks == 'both':
                            if n_e == 1:
                                elec = 0
                                if data < 0:
                                    negative_peak = True
                                    loc_peak = 'neg'
                                elif data > 0:
                                    negative_peak = False
                                    loc_peak = 'pos'
                            else:
                                if numpy.abs(numpy.max(data)) > numpy.abs(numpy.min(data)):
                                    elec = numpy.argmax(data)
                                    negative_peak = False
                                    loc_peak = 'pos'
                                else:
                                    elec = numpy.argmin(data)
                                    negative_peak = True
                                    loc_peak = 'neg'
                        else:
                            raise ValueError("unexpected value %s" % sign_peaks)

                        elec = all_elecs[elec] # elec is electrode number which has maximum peak!

                        key = '%s_%s' % (loc_peak, str(elec))

                        if result['count_%s' % key] < loop_max_elts_elec:
                            # Comment:
                            # indices => edges of the largest peaking electrode
                            # nodes_indices =>
                            # elec => electrode number with maximum peak
                            indices = nodes_indices[elec]

                            #print("elec", elec)
                            #print("indices", indices)

                            if safety_space:
                                myslice = all_times[indices, min_times[midx]:max_times[midx]]
                            else:
                                myslice = all_times[elec, min_times[midx]:max_times[midx]]

                            # Comment:
                            # do not cluster the spikes that overlaps (within the safety bound)
                            if not myslice.any():

                                # # test if the sample is pure Gaussian noise
                                if reject_noise:

                                    slice_window = local_chunk[peak - noise_window: peak + noise_window + 1, indices]
                                    values = \
                                        numpy.linalg.norm(slice_window, axis=0) / noise_levels[indices]
                                    is_noise = numpy.all(
                                        values < rejection_threshold
                                    )
                                else:
                                    is_noise = False

                                if not is_noise:
                                    # Comment:
                                    # We should not cluster spikes that are not isolated
                                    if isolation:
                                        #
                                        time_slice = numpy.arange(min_times[midx], max_times[midx])
                                        vicinity_extremas, vicinity_peaks = numpy.where(test_extremas[indices, min_times[midx]:max_times[midx]])
                                        vicinity_extremas = indices[vicinity_extremas]
                                        vicinity_peaks = local_peaktimes[0] + time_slice[vicinity_peaks]
                                        to_consider = local_chunk[vicinity_peaks, vicinity_extremas]
                                        # Comment:
                                        # Check if any of the nearby peaks is larger than the current peak -> if any, it is not isolated
                                        # Then, we do not consider such peak
                                        if negative_peak:
                                            if numpy.any(to_consider < local_chunk[peak, elec]):
                                                is_isolated = False
                                        else:
                                            if numpy.any(to_consider > local_chunk[peak, elec]):
                                                is_isolated = False

                                    if is_isolated:

                                        sub_mat = numpy.take(
                                            local_chunk[peak - duration:peak + duration + 1], indices, axis=1
                                        )

                                        if alignment:

                                            if len(indices) == 1:
                                                smoothed = True
                                                try:
                                                    f = scipy.interpolate.UnivariateSpline(
                                                        xdata, sub_mat, s=local_factors[elec], k=3
                                                    )
                                                except Exception:
                                                    smoothed = False
                                                    f = scipy.interpolate.UnivariateSpline(xdata, sub_mat, k=3, s=0)
                                                if negative_peak:
                                                    rmin = (numpy.argmin(f(cdata)) - xoff) / over_factor
                                                else:
                                                    rmin = (numpy.argmax(f(cdata)) - xoff) / over_factor
                                                if smoothed:
                                                    f = scipy.interpolate.UnivariateSpline(xdata, sub_mat, s=0, k=3)
                                                ddata = numpy.linspace(
                                                    rmin - template_shift, rmin + template_shift, n_t
                                                )
                                                sub_mat = f(ddata).astype(numpy.float32).reshape(n_t, 1)
                                            else:
                                                idx = elec_positions[elec]
                                                ydata = elec_ydata[elec]
                                                try:
                                                    f = scipy.interpolate.UnivariateSpline(
                                                        xdata, sub_mat[:, idx], s=local_factors[elec], k=3
                                                    )
                                                except Exception:
                                                    f = scipy.interpolate.UnivariateSpline(
                                                        xdata, sub_mat[:, idx], k=3, s=0
                                                    )
                                                if negative_peak:
                                                    rmin = (numpy.argmin(f(cdata)) - xoff) / over_factor
                                                else:
                                                    rmin = (numpy.argmax(f(cdata)) - xoff) / over_factor
                                                f = scipy.interpolate.RectBivariateSpline(
                                                    xdata, ydata, sub_mat, s=0, kx=3, ky=1
                                                )
                                                ddata = numpy.linspace(
                                                    rmin - template_shift, rmin + template_shift, n_t
                                                )
                                                sub_mat = f(ddata, ydata).astype(numpy.float32)

                                        if negative_peak:
                                            good_time, good_elec = numpy.unravel_index(numpy.argmin(sub_mat), sub_mat.shape)
                                        else:
                                            good_time, good_elec = numpy.unravel_index(numpy.argmax(sub_mat), sub_mat.shape)

                                        shift = template_shift - good_time
                                        is_centered = np.abs(shift) < (template_shift / 4)
                                        max_test = (good_elec == elec_positions[elec][0]) and is_centered

                                        if max_test:
                                            if gpass == 0:
                                                to_accept = True
                                                ext_amp = sub_mat[template_shift, elec_positions[elec]]
                                                result['tmp_%s_' % loc_peak + str(elec)].append(ext_amp)
                                            elif gpass == 1:

                                                if smart_searches[loc_peak][elec] > 0:

                                                    ext_amp = sub_mat[template_shift, elec_positions[elec]]
                                                    if ext_amp < result['bounds_%s_' % loc_peak + str(elec)][1]:
                                                        idx_2 = 0
                                                    elif ext_amp > result['bounds_%s_' % loc_peak + str(elec)][-2]:
                                                        idx_2 = result['nb_ss_bins_%s_' % loc_peak + str(elec)] - 1
                                                    else:
                                                        tmp = (ext_amp - result['bounds_%s_' % loc_peak + str(elec)][1]) \
                                                            /result['bin_size_%s_' % loc_peak + str(elec)]
                                                        idx_2 = int(tmp) + 1

                                                    hist = result['hist_%s_' % loc_peak + str(elec)][idx_2]
                                                    to_keep = hist < random_numbers[random_count]

                                                    if random_count == max_nb_rand_ss - 1:
                                                        random_numbers = numpy.random.rand(max_nb_rand_ss)
                                                        random_count = 0
                                                    else:
                                                        random_count += 1

                                                    if to_keep:
                                                        to_accept = True
                                                    else:
                                                        rejected += 1

                                                else:
                                                    to_accept = True

                                                if to_accept:

                                                    if use_hanning:
                                                        sub_mat *= hanning_filter

                                                    sub_mat = numpy.dot(basis['rec_%s' % loc_peak], sub_mat)
                                                    sub_mat = sub_mat.reshape((1, result['data_%s_' % loc_peak + str(elec)][0].shape[1]))
                                                    result['data_%s_' % loc_peak + str(elec)].append(sub_mat)

                                            else:

                                                if use_hanning:
                                                    sub_mat *= hanning_filter

                                                sub_mat = numpy.dot(basis['rec_%s' % loc_peak], sub_mat)
                                                sub_mat = sub_mat.reshape((1, result['pca_%s_' % loc_peak + str(elec)].shape[0]))
                                                sub_mat = numpy.dot(
                                                    sub_mat, result['pca_%s_' % loc_peak + str(elec)]
                                                )
                                                to_accept = True
                                                result['tmp_%s_' % loc_peak + str(elec)].append(sub_mat)
                                        #else:
                                        #    print "Good test failed", test_extremas[good_elec, midx]

                                    if to_accept:
                                        elt_count += 1
                                        result['count_%s_' % loc_peak + str(elec)] += 1
                                        if gpass >= 1:
                                            result['loc_times_' + str(elec)].append([peak + local_offset])
                                        if gpass == 1:
                                            result['peaks_' + str(elec)].append([negative_peak])
                                        if safety_space:
                                            all_times[indices, min_times[midx]:max_times[midx]] = True
                                        else:
                                            all_times[elec, min_times[midx]:max_times[midx]] = True
                                        test_extremas[elec, peak - local_peaktimes[0]] = False
                                else:
                                    nb_noise += 1
                                    if gpass <= 1:
                                        result['noise_times_' + str(elec)].append([peak + local_offset])

                del local_chunk

        for elec in range(n_e):
            if gpass == 1:
                result['noise_times_' + str(elec)] = numpy.concatenate(result['noise_times_' + str(elec)]).astype(numpy.uint32)
                result['peaks_' + str(elec)] = numpy.concatenate(result['peaks_' + str(elec)]).astype(numpy.uint32)
                result['loc_times_' + str(elec)] = numpy.concatenate(result['loc_times_' + str(elec)]).astype(numpy.uint32)
            elif gpass > 1:
                result['loc_times_' + str(elec)] = numpy.concatenate(result['loc_times_' + str(elec)]).astype(numpy.uint32)
            for p in search_peaks:
                if gpass == 0:
                    result['tmp_%s_' % p + str(elec)] = numpy.concatenate(result['tmp_%s_' % p + str(elec)])
                elif gpass == 1:
                    result['data_%s_' % p + str(elec)] = numpy.vstack(result['data_%s_' % p + str(elec)])
                elif gpass > 1:
                    result['tmp_%s_' % p + str(elec)] = numpy.vstack(result['tmp_%s_' % p + str(elec)])

        comm.Barrier()
        sys.stderr.flush()

        lines = [
            'Node %d has collected %d spikes and rejected %d spikes' % (comm.rank, elt_count, rejected),
            'Node %d has ignored %d noisy spikes' % (comm.rank, nb_noise)
        ]
        print_and_log(lines, 'debug', logger)
        gdata = all_gather_array(numpy.array([elt_count], dtype=numpy.float32), comm, 0)
        gdata2 = gather_array(numpy.array([rejected], dtype=numpy.float32), comm, 0)
        nb_elements = numpy.int64(numpy.sum(gdata))
        nb_rejected = numpy.int64(numpy.sum(gdata2))
        nb_total = numpy.int64(nb_elts*comm.size)

        if ((smart_search and (gpass == 0)) or (not smart_search and (gpass == 1))) and nb_elements == 0:
            if comm.rank == 0:
                print_and_log(['No waveforms found! Are the data properly loaded??'], 'error', logger)
            sys.exit(0)

        if nb_elements == 0:
            gpass = nb_repeats

        if comm.rank == 0:
            if gpass != 1:
                print_and_log(["Found %d spikes over %d requested" % (nb_elements, nb_total)], 'default', logger)
                if nb_elements == 0:
                    print_and_log(["No more spikes in the recording, stop searching"], 'info', logger)
            else:
                if isolation:
                    lines = [
                        "Found %d isolated spikes over %d requested (%d rejected)"
                        % (nb_elements, nb_total, nb_rejected)
                    ]
                    print_and_log(lines, 'default', logger)
                else:
                    lines = [
                        "Found %d spikes over %d requested (%d rejected)"
                        % (nb_elements, nb_total, nb_rejected)
                    ]
                    print_and_log(lines, 'default', logger)
                if nb_elements < 0.2 * nb_total:
                    few_elts = True

        # CLUSTERING: once we have been through enough chunks (we don't need all of them),
        # we run a clustering for each electrode.
        # print "Clustering the data..."
        local_nb_clusters = 0
        # local_hits = 0
        local_mergings = 0
        cluster_results = {}
        for p in search_peaks:
            cluster_results[p] = {}

        if gpass == 0:
            for ielec in range(n_e):
                for p in search_peaks:
                    result['tmp_%s_' % p + str(ielec)] = gather_array(
                        result['tmp_%s_' % p + str(ielec)], comm,
                        numpy.mod(ielec, comm.size), 1, compress=blosc_compress
                    )
                    result['nb_chunks_%s_' % p + str(ielec)] = gather_array(
                        result['nb_chunks_%s_' % p + str(ielec)], comm,
                        numpy.mod(ielec, comm.size), 1, compress=blosc_compress, dtype='int32'
                    )
                    result['nb_chunks_%s_' % p + str(ielec)] = numpy.sum(result['nb_chunks_%s_' % p + str(ielec)])
        elif gpass > 1:
            for ielec in range(n_e):
                for p in search_peaks:
                    result['tmp_%s_' % p + str(ielec)] = gather_array(
                        result['tmp_%s_' % p + str(ielec)], comm,
                        numpy.mod(ielec, comm.size), 1, compress=blosc_compress
                    )
        elif gpass == 1:
            for ielec in range(n_e):
                result['times_' + str(ielec)] = gather_array(
                    result['loc_times_' + str(ielec)], comm,
                    numpy.mod(ielec, comm.size), 1, compress=blosc_compress, dtype='uint32'
                )

                result['noise_times_' + str(ielec)] = gather_array(
                    result['noise_times_' + str(ielec)], comm,
                    numpy.mod(ielec, comm.size), 1, compress=blosc_compress, dtype='uint32'
                )

                result['peaks_' + str(ielec)] = gather_array(
                    result['peaks_' + str(ielec)], comm,
                    numpy.mod(ielec, comm.size), 1, compress=False, dtype='uint32'
                )

                for p in search_peaks:
                    result['data_%s_' %p + str(ielec)] = gather_array(
                        result['data_%s_' %p + str(ielec)], comm,
                        numpy.mod(ielec, comm.size), 1, compress=blosc_compress, dtype='float32'
                    )
                # if numpy.mod(ielec, comm.size) == comm.rank:
                #     print result['peaks_' + str(ielec)]

        if comm.rank == 0:
            if gpass == 0:
                print_and_log(["Estimating amplitudes distributions..."], 'default', logger)
            elif gpass == 1:
                print_and_log(["Computing density estimations..."], 'default', logger)
            else:
                print_and_log(["Refining density estimations..."], 'default', logger)
            if not os.path.exists(plot_path):
                os.makedirs(plot_path)

        if gpass == 1:
            dist_file = tempfile.NamedTemporaryFile()
            tmp_file = os.path.join(tmp_path_loc, os.path.basename(dist_file.name)) + '.hdf5'
            dist_file.close()
            result['dist_file'] = tmp_file
            tmp_h5py = h5py.File(result['dist_file'], 'w', libver='earliest')
            print_and_log(["Node %d will use temp file %s" % (comm.rank, tmp_file)], 'debug', logger)
        elif gpass > 1:
            tmp_h5py = h5py.File(result['dist_file'], 'r', libver='earliest')
        else:
            tmp_h5py = None  # default assignment (for PyCharm code inspection)

        to_explore = list(range(comm.rank, n_e, comm.size))
        sys.stderr.flush()

        if (comm.rank == 0) and gpass == nb_repeats:
            print_and_log(["Running density-based clustering..."], 'default', logger)
            to_explore = get_tqdm_progressbar(params, to_explore)

        for ielec in to_explore:

            for p in search_peaks:
                cluster_results[p][ielec] = {}

                if gpass == 0:
                    if len(result['tmp_%s_' % p + str(ielec)]) > 1:

                        # Need to estimate the number of spikes.
                        ratio = nb_chunks / float(result['nb_chunks_%s_' % p + str(ielec)])
                        ampmin = numpy.min(result['tmp_%s_' % p + str(ielec)])
                        ampmax = numpy.max(result['tmp_%s_' % p + str(ielec)])

                        if nb_ss_bins == 'auto':
                            try:
                                local_nb_bin = numpy.clip(int(numpy.abs(ampmin - ampmax)/(0.1*mads[ielec])), 50, 250)
                            except Exception:
                                local_nb_bin = 250
                        else:
                            local_nb_bin = nb_ss_bins
                        if p == 'pos':
                            if matched_filter:
                                bound = matched_thresholds_pos[ielec]
                            else:
                                bound = thresholds[ielec]
                            if bound < ampmax:
                                bins = list(numpy.linspace(bound, 1.5 * ampmax, local_nb_bin - 1))
                                bins = [-numpy.inf] + bins + [numpy.inf]
                            else:
                                bins = list(numpy.linspace(bound, bound * 10, local_nb_bin - 1))
                                bins = [-numpy.inf] + bins + [numpy.inf]
                        elif p == 'neg':
                            if matched_filter:
                                bound = -matched_thresholds_neg[ielec]
                            else:
                                bound = -thresholds[ielec]
                            if ampmin < bound:
                                bins = list(numpy.linspace(1.5 * ampmin, bound, local_nb_bin - 1))
                                bins = [-numpy.inf] + bins + [numpy.inf]
                            else:
                                bins = list(numpy.linspace(10 * bound, bound, local_nb_bin - 1))
                                bins = [-numpy.inf] + bins + [numpy.inf]
                        else:
                            raise ValueError("Unexpected value %s" % p)

                        a, b = numpy.histogram(result['tmp_%s_' % p + str(ielec)], bins)
                        nb_spikes = numpy.sum(a)
                        a = a / float(nb_spikes)
                        z = a[a > 0]
                        c = 1.0 / numpy.min(z)

                        d = numpy.ones(len(a))
                        d[a > 0] = 1. / (c * a[a > 0])
                        d = numpy.minimum(1, d)
                        d /= numpy.sum(d)
                        twist = numpy.sum(a * d)
                        factor = twist * c

                        def reject_rate(x, d, target):
                            return (numpy.mean(len(bins)*a*numpy.clip(1 - d*x, 0, 1)) - target)**2

                        target_rejection = 1 - 1/(ratio**2)
                        res = scipy.optimize.fmin(reject_rate, factor, args=(d, target_rejection), disp=False)
                        rejection_curve = numpy.clip(1 - d*res[0], 0, 1)

                        result['hist_%s_' % p + str(ielec)] = rejection_curve
                        result['bounds_%s_' % p + str(ielec)] = b
                        result['nb_ss_bins_%s_' % p + str(ielec)] = local_nb_bin

                        if debug_plots not in ['None', '']:
                            save     = [plot_path, '%s_%d.%s' %(p, ielec, make_plots)]
                            plot.view_rejection(a, b[1:], result['hist_%s_'%p + str(ielec)], save=save)

                    else:
                        # disable some electrodes
                        smart_searches[p][ielec] = 0

                    if smart_searches[p][ielec] > 0:
                        print_and_log(['Smart search is actived on channel %d' % ielec], 'debug', logger)

                elif gpass == 1:
                    if len(result['data_%s_' % p + str(ielec)]) >= 1:

                        if result['pca_%s_' % p + str(ielec)] is None:
                            if result['data_%s_' % p + str(ielec)].shape[1] > sub_output_dim:
                                pca = PCA(sub_output_dim)
                                pca.fit(result['data_%s_' % p + str(ielec)])
                                result['pca_%s_' % p + str(ielec)] = pca.components_.T.astype(numpy.float32)
                                print_and_log([
                                    "The variance explained by local PCA on electrode %s from %d %s spikes is %g with"
                                    " %d dimensions" % (
                                        ielec,
                                        len(result['data_%s_' % p + str(ielec)]),
                                        p,
                                        float(numpy.sum(pca.explained_variance_ratio_)),
                                        result['pca_%s_' % p + str(ielec)].shape[1]
                                    )
                                ], 'debug', logger)
                            # Comment:
                            # If the PCA dimension for clustering is smaller than the
                            # PCA dimension for whitening * #of nearby electrodes
                            # do not perform the clustering
                            else:
                                dimension = result['data_%s_' % p + str(ielec)].shape[1]
                                result['pca_%s_' % p + str(ielec)] = numpy.zeros(
                                    (dimension, sub_output_dim), dtype=numpy.float32
                                )
                                result['pca_%s_' % p + str(ielec)][numpy.arange(dimension), numpy.arange(dimension)] = 1

                        result['sub_%s_' % p + str(ielec)] = numpy.dot(
                            result['data_%s_' % p + str(ielec)], result['pca_%s_' % p + str(ielec)]
                        )

                        # calculates the pair of ditances between the two arbitrary array
                        rho, dist, sdist = algo.compute_rho(result['sub_%s_' % p + str(ielec)], mratio=m_ratio)
                        result['rho_%s_' % p + str(ielec)] = rho
                        result['sdist_%s_' % p + str(ielec)] = sdist
                        if hdf5_compress:
                            tmp_h5py.create_dataset(
                                'dist_%s_' % p + str(ielec), data=dist.distances, chunks=True, compression='gzip'
                            )
                        else:
                            tmp_h5py.create_dataset('dist_%s_' % p + str(ielec), data=dist.distances, chunks=True)
                        del dist, rho
                    else:
                        if result['pca_%s_' % p + str(ielec)] is None:
                            n_neighb = len(edges[nodes[ielec]])
                            dimension = basis['proj_%s' % p].shape[1] * n_neighb
                            nb_max = min(dimension, sub_output_dim)
                            result['pca_%s_' % p + str(ielec)] = numpy.zeros(
                                (dimension, sub_output_dim), dtype=numpy.float32
                            )
                            result['pca_%s_' % p + str(ielec)][numpy.arange(nb_max), numpy.arange(nb_max)] = 1
                        result['rho_%s_' % p + str(ielec)] = numpy.zeros(0, dtype=numpy.float32)
                        result['sub_%s_' % p + str(ielec)] = numpy.zeros((0, sub_output_dim), dtype=numpy.float32)
                        result['sdist_%s_' % p + str(ielec)] = numpy.zeros(0, dtype=numpy.float32)
                else:
                    if len(result['tmp_%s_' % p + str(ielec)]) > 1:

                        rho, sdist = algo.compute_rho(
                            result['sub_%s_' % p + str(ielec)],
                            update=(result['tmp_%s_' % p + str(ielec)], result['sdist_%s_' % p + str(ielec)]),
                            mratio=m_ratio
                        )
                        result['rho_%s_' % p + str(ielec)] = rho
                        result['sdist_%s_' % p + str(ielec)] = sdist
                        del rho

                if gpass == nb_repeats:  # i.e. last pass (during which clustering is done)

                    if 'tmp_%s_' % p + str(ielec) in result:
                        result.pop('tmp_%s_' % p + str(ielec))
                    n_data = len(result['data_%s_' % p + str(ielec)])
                    n_min = n_abs_min

                    if p == 'pos':
                        flag = 'positive'
                    elif p == 'neg':
                        flag = 'negative'
                    else:
                        raise ValueError("Unexpected value %s" % p)

                    if n_data > 1:
                        # dist indicates the distances
                        dist = tmp_h5py.get('dist_%s_' % p + str(ielec))[:]
                        result['rho_%s_' % p + str(ielec)] = \
                            -result['rho_%s_' % p + str(ielec)] + result['rho_%s_' % p + str(ielec)].max()

                        # Now we perform the clustering.
                        cluster_results[p][ielec]['groups'], r, d, c = algo.clustering_by_density(
                            result['rho_%s_' % p + str(ielec)], dist, n_min=n_min, alpha=sensitivity,
                            halo_rejection=halo_rejection
                        )

                        if len(c) > bad_clusters_ratio:
                            c = numpy.zeros(0, dtype=numpy.int32)
                            cluster_results[p][ielec]['groups'][:] = -1
                            lines = ["Too many centroids detected on channel %d (>%d)" %(ielec, bad_clusters_ratio),
                                     "Something wrong with the channel?",
                                     "Increase [clustering]->bad_clusters_ratio if needed"]
                            print_and_log(lines, 'debug', logger)

                        result['delta_%s_' % p + str(ielec)] = d  # i.e. save delta values

                        # Now we perform a merging step, for clusters that look too similar.
                        old_allocation = np.copy(cluster_results[p][ielec]['groups'])
                        cluster_results[p][ielec]['groups'], merged, merge_history, c = algo.merging(
                            cluster_results[p][ielec]['groups'], merging_method,
                            merging_param, result['sub_%s_' % p + str(ielec)], c
                        )

                        # Remove clusters without a sufficient number of points.
                        idx_clusters, counts = numpy.unique(cluster_results[p][ielec]['groups'], return_counts=True)
                        count = 0
                        to_remove = []

                        for label, cluster_size in zip(idx_clusters, counts):
                            if (label > -1) and (cluster_size < n_min):
                                tmp = cluster_results[p][ielec]['groups'] == label
                                cluster_results[p][ielec]['groups'][tmp] = -1
                                to_remove += [count]
                            count += 1

                        c = numpy.delete(c, to_remove)  # update the cluster labels

                        # Sanity plots for clusters.
                        if make_plots not in ['None', '']:
                            save = [plot_path, '%s_%d.%s' % (p, ielec, make_plots)]
                            injected = None
                            if test_clusters:
                                injected = numpy.zeros(len(result['data_%s_' % p + str(ielec)]), dtype=numpy.bool_)
                                key = 'spikes_' + str(ielec)
                                thresh = 2
                                if key in injected_spikes:
                                    for icount, spike in enumerate(result['times_' + str(ielec)]):
                                        idx = numpy.where(
                                            numpy.abs(spike - injected_spikes['spikes_' + str(ielec)]) < thresh
                                        )[0]
                                        if len(idx) > 0:
                                            if icount < (len(injected) - 1):
                                                injected[icount] = True

                            plot.view_clusters(
                                result['sub_%s_' % p + str(ielec)], result['rho_%s_' % p + str(ielec)],
                                result['delta_%s_' % p + str(ielec)], c,
                                cluster_results[p][ielec]['groups'], injected=injected,
                                save=save, alpha=sensitivity
                            )

                        # Sanity plots for local merges.
                        if debug_plots not in ['None', '']:
                            # Retrieve waveforms data.
                            n_neighbors = len(edges[nodes[ielec]])
                            indices = nodes_indices[ielec]
                            data = result['data_%s_' % p + str(ielec)]
                            data = data.reshape((n_data, basis['proj_%s' % p].shape[1], n_neighbors))
                            idx = numpy.where(indices == ielec)[0][0]
                            sub_data = numpy.take(data, idx, axis=2)
                            waveforms_data = numpy.dot(sub_data, basis['rec_%s' % p])
                            # Retrieve clusters data.
                            clusters_data = result['sub_%s_' % p + str(ielec)]
                            # Retrieve new allocation.
                            new_allocation = cluster_results[p][ielec]['groups']
                            # Define output path.
                            save = [plot_path, '%s_%d' % (p, ielec), debug_plots]
                            # Call plot function.
                            plot.view_local_merges(
                                waveforms_data,
                                clusters_data,
                                old_allocation,
                                new_allocation,
                                merge_history,
                                save=save
                            )

                        keys = [
                            'loc_times_' + str(ielec),
                            'all_times_' + str(ielec),
                        ]
                        if not debug:
                            keys += [
                                'delta_%s_' % p + str(ielec),
                                'rho_%s_' % p + str(ielec),
                            ]

                        for key in keys:
                            if key in result:
                                result.pop(key)

                        mask = numpy.where(cluster_results[p][ielec]['groups'] > -1)[0]
                        cluster_results[p][ielec]['n_clus'] = \
                            len(numpy.unique(cluster_results[p][ielec]['groups'][mask]))
                        n_clusters = []
                        result['clusters_%s_' % p + str(ielec)] = cluster_results[p][ielec]['groups']

                        for i in numpy.unique(cluster_results[p][ielec]['groups'][mask]):
                            n_clusters += [numpy.sum(cluster_results[p][ielec]['groups'][mask] == i)]

                        line = [
                            "Node %d: %d-%d %s templates on channel %d from %d spikes: %s"
                            % (comm.rank, merged[0], merged[1], flag, ielec, n_data, str(n_clusters))
                        ]
                        print_and_log(line, 'debug', logger)
                        local_mergings += merged[1]
                        del dist, d, c
                    else:
                        cluster_results[p][ielec]['groups'] = numpy.zeros(0, dtype=numpy.int32)
                        cluster_results[p][ielec]['n_clus'] = 0
                        result['clusters_%s_' % p + str(ielec)] = numpy.zeros(0, dtype=numpy.int32)
                        result['delta_%s_' % p + str(ielec)] = numpy.zeros(0, dtype=numpy.float32)
                        line = ["Node %d: not enough %s spikes on channel %d" % (comm.rank, flag, ielec)]
                        print_and_log(line, 'debug', logger)

                    local_nb_clusters += cluster_results[p][ielec]['n_clus']

        if gpass >= 1:
            tmp_h5py.close()
        gpass += 1

    sys.stderr.flush()
    try:
        os.remove(result['dist_file'])
    except OSError:
        pass

    comm.Barrier()

    # gdata = gather_array(numpy.array([local_hits], dtype=numpy.float32), comm, 0)
    gdata2 = gather_array(numpy.array([local_mergings], dtype=numpy.float32), comm, 0)
    gdata3 = gather_array(numpy.array([local_nb_clusters], dtype=numpy.float32), comm, 0)

    if comm.rank == 0:
        # total_hits = int(numpy.sum(gdata))
        total_mergings = int(numpy.sum(gdata2))
        total_nb_clusters = int(numpy.sum(gdata3))
        lines = [
            "Number of clusters found : %d" % total_nb_clusters,
            "Number of local merges   : %d (method %s, param %g)" % (total_mergings, merging_method, merging_param)
        ]
        if few_elts:
            lines += ["Not enough spikes gathered: -put safety_space=False?"]
            if numpy.any(sdata > 0):
                lines += ["                            -remove smart_search?"]

        print_and_log(lines, 'info', logger)
        print_and_log(["Estimating the templates with the %s procedure ..." % extraction], 'default', logger)
        if use_savgol:
            print_and_log(["Templates will be smoothed by Savitzky Golay Filtering ..."], 'debug', logger)

    # Comment:
    # Now we perform the extraction of the templates.
    # This part is the key to generating the templates
    temp_x = [numpy.zeros(0, dtype=numpy.uint32)]
    temp_y = [numpy.zeros(0, dtype=numpy.uint32)]
    temp_data = [numpy.zeros(0, dtype=numpy.float32)]
    templates_to_remove = [numpy.empty(0, dtype=numpy.int32)]

    # FIXME
    # analysis_file = open('analysis_file-%d.dat' % comm.rank, 'w')
    # total_elec_in_template = 0
    # total_elec_in_pruned_template = 0

    if extraction in ['median-raw', 'mean-raw']:

        total_nb_clusters = int(comm.bcast(numpy.array([int(numpy.sum(gdata3))], dtype=numpy.int32), root=0)[0])
        offsets = numpy.zeros(comm.size, dtype=numpy.int32)
        for i in range(comm.size-1):
            offsets[i + 1] = comm.bcast(numpy.array([local_nb_clusters], dtype=numpy.int32), root=i)
        node_pad = numpy.sum(offsets[:comm.rank+1])

        if parallel_hdf5:
            hfile = h5py.File(file_out_suff + '.templates.hdf5', 'w', driver='mpio', comm=comm, libver='earliest')
            norms = hfile.create_dataset('norms', shape=(2 * total_nb_clusters, ), dtype=numpy.float32, chunks=True)
            electrodes = hfile.create_dataset('electrodes', shape=(total_nb_clusters, ), dtype=numpy.int32, chunks=True)
            local_clusters = hfile.create_dataset('local_clusters', shape=(total_nb_clusters,), dtype=numpy.int32, chunks=True)
            if not fixed_amplitudes:
                amps_lims = hfile.create_dataset('limits', shape=(total_nb_clusters, nb_amp_times, 2), dtype=numpy.float32, chunks=True)
            else:
                amps_lims = hfile.create_dataset('limits', shape=(total_nb_clusters, 2), dtype=numpy.float32, chunks=True)
            supports = hfile.create_dataset('supports', shape=(total_nb_clusters, n_e), dtype=numpy.bool_, chunks=True)
            g_count = node_pad
            g_offset = total_nb_clusters
        else:
            hfile = h5py.File(file_out_suff + '.templates-%d.hdf5' % comm.rank, 'w', libver='earliest')
            electrodes = hfile.create_dataset('electrodes', shape=(local_nb_clusters, ), dtype=numpy.int32, chunks=True)
            local_clusters = hfile.create_dataset('local_clusters', shape=(local_nb_clusters,), dtype=numpy.int32, chunks=True)
            norms = hfile.create_dataset('norms', shape=(2*local_nb_clusters, ), dtype=numpy.float32, chunks=True)
            if not fixed_amplitudes:
                amps_lims = hfile.create_dataset('limits', shape=(local_nb_clusters, nb_amp_times, 2), dtype=numpy.float32, chunks=True)
            else:
                amps_lims = hfile.create_dataset('limits', shape=(local_nb_clusters, 2), dtype=numpy.float32, chunks=True)
            supports = hfile.create_dataset('supports', shape=(local_nb_clusters, n_e), dtype=numpy.bool_, chunks=True)
            g_count = 0
            g_offset = local_nb_clusters

        comm.Barrier()
        cfile = h5py.File(file_out_suff + '.clusters-%d.hdf5' % comm.rank, 'w', libver='earliest')
        count_templates = node_pad

        data_file.close()

        to_explore = list(range(comm.rank, n_e, comm.size))

        if comm.rank == 0:
            to_explore = get_tqdm_progressbar(params, to_explore)

        for ielec in to_explore:

            nb_dim_kept = numpy.inf
            for p in search_peaks:
                nb_dim_kept = min(nb_dim_kept, result['pca_%s_' % p + str(ielec)].shape[1])

            result['data_' + str(ielec)] = [numpy.empty((0, nb_dim_kept), dtype=numpy.float32)]
            if debug:
                result['rho_' + str(ielec)] = [numpy.empty(0, dtype=numpy.float32)]
                result['delta_' + str(ielec)] = [numpy.empty(0, dtype=numpy.float32)]

            # The indices here refers to all the electrodes in the same shank
            shank_nodes, _ = get_nodes_and_edges(params, shank_with=nodes[ielec])
            indices = inv_nodes[shank_nodes]

            for p in search_peaks:

                mask = numpy.where(cluster_results[p][ielec]['groups'] > -1)[0]

                if p == 'pos':
                    myslice2 = numpy.where(result['peaks_' + str(ielec)] == 0)[0]
                elif p == 'neg':
                    myslice2 = numpy.where(result['peaks_' + str(ielec)] == 1)[0]
                else:
                    raise ValueError("unexpected value")

                loc_times = numpy.take(result['times_' + str(ielec)], myslice2)
                loc_clusters = numpy.take(cluster_results[p][ielec]['groups'], mask)

                # Comment:
                # We generate templates only when the clustering returns valid results
                for group in numpy.unique(loc_clusters):

                    electrodes[g_count] = ielec
                    local_clusters[g_count] = group

                    myslice = numpy.where(cluster_results[p][ielec]['groups'] == group)[0]

                    if fine_amplitude:
                        data = result['sub_%s_' % p + str(ielec)][myslice]
                        centroid = numpy.median(data, 0)
                        centroid = centroid.reshape(1, len(centroid))
                        distances = \
                            scipy.spatial.distance.cdist(data, centroid, 'euclidean').flatten()
                        labels_i = myslice[numpy.argsort(distances)[:nb_snippets]]
                    else:
                        labels_i = numpy.random.permutation(myslice)[:nb_snippets]

                    times_i = numpy.take(loc_times, labels_i)
                    labels_i = numpy.ones(len(times_i), dtype=numpy.int32)

                    # neighs = indices => Indicates that the Spyking Circus retrieves all the waveforms in the same shank
                    # We should modify this code to retrieve only the data from the nearby electrodes
                    sub_data, sub_data_raw = io.get_stas(params, times_i, labels_i, ielec, neighs=indices, nodes=nodes, pos=p, raw_snippets=True)

                    if extraction == 'median-raw':
                        first_component = numpy.median(sub_data, 0)
                    elif extraction == 'mean-raw':
                        first_component = numpy.mean(sub_data, 0)
                    else:
                        raise ValueError("unexpected value %s" % extraction)

                    # FIXME (Spatial)
                    # may need to change this code for Savitzky Golay Filtering
                    if use_savgol and savgol_window > 3:
                        min_value = first_component[elec_positions_shanks[ielec], template_shift]
                        tmp_fast = scipy.signal.savgol_filter(first_component, savgol_window, 3, axis=1)
                        tmp_slow = scipy.signal.savgol_filter(first_component, 3 * savgol_window, 3, axis=1)
                        first_component = centered_filter * tmp_fast + (1 - centered_filter) * tmp_slow
                        first_component[elec_positions_shanks[ielec], template_shift] = min_value

                    # FIXME (Spatial)
                    # may need to utilize this code to sparsify the template
                    # the code removes the electrodes (from the templates) that change
                    # by only a small amount for the given peak

                    # compress templates
                    if comp_templates:
                        local_stds = numpy.std(first_component, 1)
                        # 1. find maximum local_stds / stds[indices] - leave only one electrode, regardless of sparsify value
                        #target_list = local_stds / stds[indices]
                        #max_idx = numpy.argmax(target_list)
                        #to_delete = numpy.where(numpy.logical_not(indices == max_idx))[0]

                        # 2. original code
                        # to_delete = numpy.where(local_stds / stds[indices] < sparsify)[0] # find the elec idxs of first component(template?)with small stds over n_t relative to stds[indices] ; stds given as parameter, indices simply all elecs in the same shank

                        # 3. leave electrodes within predefined radius : sparsify_radius(um)
                        target_list = local_stds / stds[indices]
                        max_idx = numpy.argmax(target_list)
                        local_max_position = positions[max_idx]
                        to_delete = numpy.where(local_stds / stds[indices] < sparsify)[0]

                        # convert to list
                        to_delete = list(to_delete)
                        num_delete = len(to_delete)
                        # to print how many electrodes are pruned
                        num_elec = len(local_stds)
                        elec_in_template = num_elec - num_delete
                        num_prune = 0
                        if radius_en:
                            for elec in range(len(local_stds)):
                                distance = numpy.linalg.norm(positions[elec] - local_max_position)
                                if distance > sparsify_radius and (elec not in to_delete):
                                    # print("distance", distance)
                                    num_prune += 1
                                    to_delete.append(elec)

                        # elec in pruned template
                        elec_in_pruned_template = num_elec - len(to_delete)

                        # revert to numpy array
                        to_delete = numpy.array(to_delete)

                        print(f"{num_prune} electrodes pruned out of {elec_in_template}, {elec_in_pruned_template} electrodes left")

                        if len(to_delete) == 0:
                            to_delete = numpy.empty(0, dtype=int)

                    else:
                        to_delete = numpy.empty(0)  # i.e. no channel to silence

                    # first component : primary template (centroid of cluster)
                    first_component[to_delete, :] = 0
                    sub_data_raw[:, to_delete, :] = 0

                    if p == 'neg':
                        tmpidx = numpy.unravel_index(first_component.argmin(), first_component.shape)
                        ratio = -thresholds[indices[tmpidx[0]]] / first_component[tmpidx[0]].min()
                    elif p == 'pos':
                        tmpidx = numpy.unravel_index(first_component.argmax(), first_component.shape)
                        ratio = thresholds[indices[tmpidx[0]]] / first_component[tmpidx[0]].max()
                    else:
                        raise ValueError("Unexpected value %s" % p)

                    shift = template_shift - tmpidx[1]

                    templates = numpy.zeros((n_e, n_t), dtype=numpy.float32)
                    sub_data_aligned = numpy.zeros(sub_data_raw.shape, dtype=numpy.float32)
                    if shift > 0:
                        templates[indices, shift:] = first_component[:, :-shift]
                        sub_data_aligned[:, :, shift:] = sub_data_raw[:, :, :-shift]
                    elif shift < 0:
                        templates[indices, :shift] = first_component[:, -shift:]
                        sub_data_aligned[:, :, :shift] = sub_data_raw[:, :, -shift:]
                    else:
                        templates[indices, :] = first_component
                        sub_data_aligned = sub_data_raw

                    x, y, z = sub_data_aligned.shape
                    sub_data_flat_raw = sub_data_aligned.reshape(x, y * z)

                    normed_template = templates[indices].flatten()/numpy.sqrt(numpy.sum(templates ** 2) / n_scalar)

                    # The residual indicates the difference between the template
                    # Refer to template matching step 5
                    amplitudes = sub_data_flat_raw.dot(normed_template)
                    residuals = sub_data_flat_raw - amplitudes[:, numpy.newaxis] * normed_template/n_scalar

                    residuals = residuals.reshape(x, y, z)
                    channel_mads = numpy.median(numpy.abs(residuals - numpy.median(residuals, 0)), 0)
                    channel_mads[to_delete, :] = 0
                    frac_high_variances = numpy.max(channel_mads.max(1)/mads[indices])

                    is_noise = (len(to_delete) / len(indices) >= sparsity_limit) or \
                               ((1 / ratio) < noise_thresh) or \
                               (frac_high_variances > ignored_mixtures)

                    if debug_plots not in ['None', '']:
                        save     = [plot_path, '%s_%d_t%d.%s' %(p, ielec, count_templates, make_plots)]
                        plot.variance_template(first_component, channel_mads, mads[indices], save=save)

                    # FIXME (Spatial)
                    # May need to check this code. (Removes templates with high noise)
                    if is_noise:
                        templates_to_remove.append(numpy.array([count_templates], dtype='int32'))
                    else:
                        # COMMENT
                        # save templates here -> temp_x, temp_y, temp_data
                        templates = templates.ravel()
                        dx = templates.nonzero()[0].astype(numpy.uint32)
                        temp_x.append(dx)
                        temp_y.append(count_templates * numpy.ones(len(dx), dtype=numpy.uint32))
                        temp_data.append(templates[dx])

                        to_keep = numpy.delete(indices, to_delete)
                        supports[g_count, to_keep] = True
                        norms[g_count] = numpy.sqrt(numpy.sum(templates.ravel() ** 2) / n_scalar)

                        if fine_amplitude:
                            amp_min = 0.75
                            amp_max = 1.25
                        else:
                            x, y, z = sub_data_raw.shape
                            sub_data_raw[:, to_delete, :] = 0
                            sub_data_flat_raw = sub_data_raw.reshape(x, y * z)
                            first_flat = first_component.reshape(y * z, 1)
                            amplitudes = numpy.dot(sub_data_flat_raw, first_flat)
                            amplitudes /= numpy.sum(first_flat ** 2)
                            center = 1 #numpy.median(amplitudes)  # TODO remove this line?
                            variation = numpy.median(numpy.abs(amplitudes - center))
                            distance = \
                            min(0, numpy.abs(first_component[tmpidx[0], tmpidx[1]]) - thresholds[indices[tmpidx[0]]])
                            noise_limit = max([0, distance + mads[indices[tmpidx[0]]]])
                            amp_min = center - min([dispersion[0] * variation, noise_limit])
                            amp_max = center + min([dispersion[1] * variation, mads[indices[tmpidx[0]]]])

                        if not fixed_amplitudes:
                            data = numpy.ones((nb_amp_times, 2), dtype=numpy.float32)
                            data[:, 0] = 0.5
                            data[:, 1] = 1.5
                            amps_lims[g_count] = data
                        else:
                            amps_lims[g_count] = [amp_min, amp_max]

                        offset = total_nb_clusters + count_templates
                        sub_templates = numpy.zeros((n_e, n_t), dtype=numpy.float32)

                        if two_components:
                            ortho_templates = numpy.median(residuals, 0).reshape(len(indices), n_t)
                            sub_templates[indices] = ortho_templates

                        sub_templates = sub_templates.ravel()
                        dx = sub_templates.nonzero()[0].astype(numpy.uint32)
                        temp_x.append(dx)
                        temp_y.append(offset * numpy.ones(len(dx), dtype=numpy.uint32))
                        temp_data.append(sub_templates[dx])

                        norms[g_count + g_offset] = numpy.sqrt(numpy.sum(sub_templates.ravel() ** 2) / n_scalar)

                    count_templates += 1
                    g_count += 1

                nb_dim_found = result['sub_%s_' % p + str(ielec)].shape[1]

                if nb_dim_kept == nb_dim_found:
                    result['data_' + str(ielec)].append(result['sub_%s_' % p + str(ielec)])
                else:
                    sliced_data = result['sub_%s_' % p + str(ielec)][:, :nb_dim_kept]
                    result['data_' + str(ielec)].append(sliced_data)
                if len(result['clusters_' + str(ielec)]) > 0:
                    max_offset = numpy.int32(numpy.max(result['clusters_' + str(ielec)]) + 1)
                else:
                    max_offset = numpy.int32(0)

                if debug:
                    result['rho_' + str(ielec)].append(result['rho_%s_' % p + str(ielec)])
                    result['delta_' + str(ielec)].append(result['delta_%s_' % p + str(ielec)])

                mask = result['clusters_%s_' % p + str(ielec)] > -1
                result['clusters_%s_' % p + str(ielec)][mask] += max_offset
                result['clusters_' + str(ielec)] = numpy.concatenate(
                    (result['clusters_' + str(ielec)],
                     result['clusters_%s_' % p + str(ielec)])
                )

            # Final concatenations (for efficiency).
            result['data_' + str(ielec)] = numpy.concatenate(result['data_' + str(ielec)])
            if debug:
                result['rho_' + str(ielec)] = numpy.concatenate(result['rho_' + str(ielec)])
                result['delta_' + str(ielec)] = numpy.concatenate(result['delta_' + str(ielec)])

            all_indices = [numpy.empty(0, dtype=numpy.uint32)]
            for p in search_peaks:
                if p == 'pos':
                    target = 0
                elif p == 'neg':
                    target = 1
                else:
                    raise ValueError("unexpected value")
                indices_ = numpy.where(result['peaks_' + str(ielec)] == target)[0]
                all_indices.append(indices_)
            all_indices = numpy.concatenate(all_indices)  # i.e. concatenate once for efficiency

            result['times_' + str(ielec)] = result['times_' + str(ielec)][all_indices]
            result['peaks_' + str(ielec)] = result['peaks_' + str(ielec)][all_indices]

            io.write_datasets(cfile, to_write, result, ielec, compression=hdf5_compress)

        # At the end we should have a templates variable to store.
        cfile.flush()
        cfile.close()
        del result, amps_lims
        sys.stderr.flush()

        temp_x = numpy.concatenate(temp_x)
        temp_y = numpy.concatenate(temp_y)
        temp_data = numpy.concatenate(temp_data)
        # FIXME
        # collect all the analysis info from the processes
        # analysis_file.write(f"{total_elec_in_template}, {total_elec_in_pruned_template}\n")
        # analysis_file.close()

        comm.Barrier()

        # collect analysis result from all comm.rank files
        # if comm.rank == 0:
        #     sum_analysis_file = open('summary_analysis_file.dat', 'w')
        #     sum_elec_in_template = 0
        #     sum_elec_in_pruned_template = 0
        #     for i in range(comm.size):
        #         temp_analysis_file = open('analysis_file-%d.dat' % i, 'r')
        #         total_elec_in_template, total_elec_in_pruned_template = temp_analysis_file.readlines()[-1].split(',')
        #         sum_elec_in_template += int(total_elec_in_template)
        #         sum_elec_in_pruned_template += int(total_elec_in_pruned_template)
        #         temp_analysis_file.close()
        #         os.remove('analysis_file-%d.dat' % i)
        #     sum_analysis_file.write(f"{sum_elec_in_template}, {sum_elec_in_pruned_template}\n")
        #     sum_analysis_file.close()

        templates_to_remove = np.concatenate(templates_to_remove)  # i.e. concatenate once for efficiency
        templates_to_remove = all_gather_array(templates_to_remove, comm, 0, dtype='int32')

        # We need to gather the sparse arrays.
        temp_x = gather_array(temp_x, comm, dtype='uint32', compress=blosc_compress)
        temp_y = gather_array(temp_y, comm, dtype='uint32', compress=blosc_compress)
        temp_data = gather_array(temp_data, comm)

        if parallel_hdf5:
            if comm.rank == 0:
                rs = [
                    h5py.File(file_out_suff + '.clusters-%d.hdf5' % i, 'r', libver='earliest')
                    for i in range(comm.size)
                ]
                cfile = h5py.File(file_out_suff + '.clusters.hdf5', 'w', libver='earliest')
                io.write_datasets(
                    cfile,
                    ['electrodes', 'local_clusters'],
                    {'electrodes': electrodes[:], 'local_clusters': local_clusters[:]},
                )
                for i in range(comm.size):
                    for j in range(i, n_e, comm.size):
                        io.write_datasets(cfile, to_write, rs[i], j, compression=hdf5_compress)
                    rs[i].close()
                    os.remove(file_out_suff + '.clusters-%d.hdf5' % i)
                cfile.flush()
                cfile.close()
            hfile.flush()
            hfile.close()
        else:
            hfile.flush()
            hfile.close()
            comm.Barrier()
            if comm.rank == 0:
                ts = [
                    h5py.File(file_out_suff + '.templates-%d.hdf5' % i, 'r', libver='earliest')
                    for i in range(comm.size)
                ]
                rs = [
                    h5py.File(file_out_suff + '.clusters-%d.hdf5' % i, 'r', libver='earliest')
                    for i in range(comm.size)
                ]
                hfile = h5py.File(file_out_suff + '.templates.hdf5', 'w', libver='earliest')
                cfile = h5py.File(file_out_suff + '.clusters.hdf5', 'w', libver='earliest')
                electrodes = hfile.create_dataset(
                    'electrodes', shape=(total_nb_clusters, ), dtype=numpy.int32, chunks=True
                )
                local_clusters = hfile.create_dataset(
                    'local_clusters', shape=(total_nb_clusters,), dtype=numpy.int32, chunks=True
                )
                norms = hfile.create_dataset(
                    'norms', shape=(2 * total_nb_clusters, ), dtype=numpy.float32, chunks=True
                )
                if not fixed_amplitudes:
                    amplitudes = hfile.create_dataset(
                        'limits', shape=(total_nb_clusters, nb_amp_times, 2), dtype=numpy.float32, chunks=True
                    )
                else:
                    amplitudes = hfile.create_dataset(
                        'limits', shape=(total_nb_clusters, 2), dtype=numpy.float32, chunks=True
                    )
                supports = hfile.create_dataset(
                    'supports', shape=(total_nb_clusters, n_e), dtype=numpy.bool_, chunks=True
                )
                count = 0
                for i in range(comm.size):
                    loc_norms = ts[i].get('norms')
                    middle = len(loc_norms) // 2
                    norms[count:count+middle] = loc_norms[:middle]
                    norms[total_nb_clusters+count:total_nb_clusters+count+middle] = loc_norms[middle:]
                    electrodes[count:count+middle] = ts[i].get('electrodes')
                    local_clusters[count:count+middle] = ts[i].get('local_clusters')
                    amplitudes[count:count+middle] = ts[i].get('limits')
                    supports[count:count+middle] = ts[i].get('supports')
                    count += middle
                    for j in range(i, n_e, comm.size):
                        io.write_datasets(cfile, to_write, rs[i], j, compression=hdf5_compress)
                    ts[i].close()
                    rs[i].close()
                    os.remove(file_out_suff + '.templates-%d.hdf5' % i)
                    os.remove(file_out_suff + '.clusters-%d.hdf5' % i)
                hfile.flush()  # we need to flush otherwise electrodes[:] refers to zeros and not the real values
                io.write_datasets(
                    cfile,
                    ['electrodes', 'local_clusters'],
                    {'electrodes': electrodes[:], 'local_clusters': local_clusters[:]},
                )
                cfile.flush()
                hfile.close()
                cfile.close()

        if comm.rank == 0:
            hfile = h5py.File(file_out_suff + '.templates.hdf5', 'r+', libver='earliest')
            if hdf5_compress:
                # save template here
                hfile.create_dataset('temp_x', data=temp_x, compression='gzip')
                hfile.create_dataset('temp_y', data=temp_y, compression='gzip')
                hfile.create_dataset('temp_data', data=temp_data, compression='gzip')
            else:
                hfile.create_dataset('temp_x', data=temp_x)
                hfile.create_dataset('temp_y', data=temp_y)
                hfile.create_dataset('temp_data', data=temp_data)
            hfile.create_dataset('temp_shape', data=numpy.array([n_e, n_t, 2 * total_nb_clusters], dtype=numpy.int32))
            hfile.flush()
            hfile.close()

    else:  # extraction not in ['median-raw', 'mean-raw']

        raise ValueError("Unexpected value %s" % extraction)


    del temp_x, temp_y, temp_data

    import gc
    gc.collect()

    comm.Barrier()

    if len(templates_to_remove) > 0:

        if comm.rank == 0:
            print_and_log(
                ["Removing %d strongly shifted or noisy/mixture templates..." % len(templates_to_remove)], 'default', logger
            )

        if comm.rank == 0:
            result = io.load_data(params, 'clusters')
        else:
            result = []

        algo.slice_templates(params, to_remove=templates_to_remove)
        algo.slice_clusters(params, to_remove=templates_to_remove, result=result)

        del result

    gc.collect()
    comm.Barrier()

    # total number of clusters == number of templates // 2
    # because there are 2 types of templates (primary, secondary)
    total_nb_clusters = int(io.load_data(params, 'nb_templates') // 2)

    if total_nb_clusters > 0:

        supports = io.load_data(params, 'supports')
        median_channels = numpy.median(numpy.sum(supports, 1))
        if median_channels < low_channels_thr:
            #templates_normalization = False
            params.set('clustering', 'cc_merge', 1)

            if comm.rank == 0:
                #print_and_log(['Templates on few channels only (%g), turning off normalization' %median_channels], 'info', logger)
                print_and_log(["Templates on few channels only (%g), cc_merge set to 1 automatically" %median_channels], 'info', logger)

        if comm.rank == 0 and (params.getfloat('clustering', 'cc_merge') < 1):
            print_and_log(["Merging similar templates..."], 'default', logger)

        merged1 = algo.merging_cc(params, nb_cpu=nb_cpu, nb_gpu=nb_gpu, use_gpu=use_gpu)
        comm.Barrier()
        gc.collect()

        if remove_mixture:
            if comm.rank == 0:
                print_and_log(["Removing mixtures of templates..."], 'default', logger)
            merged2 = algo.delete_mixtures(params, nb_cpu=nb_cpu, nb_gpu=nb_gpu, use_gpu=use_gpu, debug_plots=debug_plots)
        else:
            merged2 = [0, 0]
        comm.Barrier()
        gc.collect()
    else:
        merged1 = [0, 0]
        merged2 = [0, 0]

    sys.stderr.flush()
    if comm.rank == 0:

        lines = [
            "Number of global merges    : %d" % merged1[1],
            "Number of mixtures removed : %d" % merged2[1],
        ]
        print_and_log(lines, 'info', logger)

    comm.Barrier()

    if (fine_amplitude) or (debug_plots not in ['None', '']):

        if comm.rank == 0 and fine_amplitude:
            print_and_log(["Computing optimal amplitudes for the templates..."], 'default', logger)
        elif comm.rank == 0 and (debug_plots not in ['None', '']):
            print_and_log(["Plotting amplitudes snippets..."], 'default', logger)

        algo.refine_amplitudes(
            params, nb_cpu=nb_cpu, nb_gpu=nb_gpu, use_gpu=use_gpu,
            normalization=templates_normalization, debug_plots=debug_plots
        )
    comm.Barrier()
    gc.collect()
    sys.stderr.flush()

    # Comment:
    # Precalculate the correlation between
    # 1) different templates
    # 2) for different time intervals
    io.get_overlaps(
        params, erase=True, normalize=templates_normalization, nb_cpu=nb_cpu, nb_gpu=nb_gpu, use_gpu=use_gpu
    )

    comm.Barrier()
    gc.collect()
    sys.stderr.flush()

    if SHARED_MEMORY and ignore_dead_times:
        mpi_memory_3.Free()
