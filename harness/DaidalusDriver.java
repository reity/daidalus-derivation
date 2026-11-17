import gov.nasa.larcfm.ACCoRD.ConflictData;
import gov.nasa.larcfm.ACCoRD.WCVTable;
import gov.nasa.larcfm.ACCoRD.WCV_TAUMOD;
import gov.nasa.larcfm.Util.Vect3;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Harness around the unmodified DAIDALUS Java classes (nasa/daidalus at commit 1c7b58e5).
 *
 * <pre>
 * run   vectors.csv results.csv  time_in, time_out, conflict(), violation(), and conflict(B, T)
 * tables                         default threshold tables (cross-check of ENV-3)
 * bench vectors.csv passes       time and bytes allocated per call of conflictDetection and violation
 * </pre>
 */
public final class DaidalusDriver {
    /** Numeric columns of a test vector, in the order used below. */
    static final String[] FIELDS = {
        "sox", "soy", "soz", "vox", "voy", "voz", "six", "siy", "siz", "vix", "viy", "viz",
        "B", "T", "DTHR", "ZTHR", "TTHR", "TCOA"
    };

    /** Sink that keeps the benchmark loops from being optimized away. */
    static volatile double sink;

    private DaidalusDriver() {
    }

    /** Rows of a test-vector file, with the index of each column. */
    record Table(List<String[]> rows, Map<String, Integer> columns) {
    }

    static double number(String text) {
        switch (text) {
            case "nan": return Double.NaN;
            case "inf": return Double.POSITIVE_INFINITY;
            case "-inf": return Double.NEGATIVE_INFINITY;
            default: return Double.parseDouble(text);
        }
    }

    static Table load(String path) throws IOException {
        List<String[]> rows = new ArrayList<>();
        Map<String, Integer> columns = new HashMap<>();
        try (BufferedReader reader = new BufferedReader(new FileReader(path))) {
            String[] header = reader.readLine().split(",", -1);
            for (int i = 0; i < header.length; i++) {
                columns.put(header[i], i);
            }
            String line;
            while ((line = reader.readLine()) != null) {
                rows.add(line.split(",", -1));
            }
        }
        return new Table(rows, columns);
    }

    static double[] values(Table table, String[] row) {
        double[] v = new double[FIELDS.length];
        for (int i = 0; i < FIELDS.length; i++) {
            v[i] = number(row[table.columns().get(FIELDS[i])]);
        }
        return v;
    }

    /** Detector with the thresholds of a vector, built the way DAIDALUS builds a WCVTable. */
    static WCV_TAUMOD detector(double[] v) {
        return new WCV_TAUMOD("", new WCVTable(v[14], v[15], v[16], v[17]));
    }

    static String flag(boolean x) {
        return x ? "1" : "0";
    }

    public static void main(String[] arguments) throws IOException {
        String command = arguments.length > 0 ? arguments[0] : "";
        if (command.equals("run") && arguments.length == 3) {
            run(arguments[1], arguments[2]);
        } else if (command.equals("tables") && arguments.length == 1) {
            tables();
        } else if (command.equals("bench") && arguments.length == 3) {
            bench(arguments[1], Integer.parseInt(arguments[2]));
        } else {
            System.err.println("usage: DaidalusDriver run <vectors.csv> <results.csv> | tables"
                    + " | bench <vectors.csv> <passes>");
            System.exit(1);
        }
    }

    static void tables() {
        WCVTable defaults = new WCVTable();
        System.out.println("default DTHR=" + defaults.getDTHR() + " ZTHR=" + defaults.getZTHR()
                + " TTHR=" + defaults.getTTHR() + " TCOA=" + defaults.getTCOA());
        String[] names = {
            "DO_365_Phase_I_preventive", "DO_365_DWC_Phase_I", "DO_365_DWC_Phase_II",
            "DO_365_DWC_Non_Coop", "Buffered_Phase_I_preventive", "Buffered_DWC_Phase_I"
        };
        WCVTable[] tables = {
            WCVTable.DO_365_Phase_I_preventive, WCVTable.DO_365_DWC_Phase_I,
            WCVTable.DO_365_DWC_Phase_II, WCVTable.DO_365_DWC_Non_Coop,
            WCVTable.Buffered_Phase_I_preventive, WCVTable.Buffered_DWC_Phase_I
        };
        for (int i = 0; i < tables.length; i++) {
            System.out.println(names[i] + " " + tables[i].getDTHR() + " " + tables[i].getZTHR()
                    + " " + tables[i].getTTHR() + " " + tables[i].getTCOA());
        }
    }

    static void run(String input, String output) throws IOException {
        Table table = load(input);
        try (PrintWriter writer = new PrintWriter(new BufferedWriter(new FileWriter(output)))) {
            writer.println("id,t_in,t_out,conflict,violation,conflict_bt,error");
            for (String[] row : table.rows()) {
                String id = row[table.columns().get("id")];
                try {
                    double[] v = values(table, row);
                    WCV_TAUMOD wcv = detector(v);
                    Vect3 so = new Vect3(v[0], v[1], v[2]);
                    Vect3 vo = new Vect3(v[3], v[4], v[5]);
                    Vect3 si = new Vect3(v[6], v[7], v[8]);
                    Vect3 vi = new Vect3(v[9], v[10], v[11]);
                    ConflictData cd = wcv.conflictDetection(so, vo, si, vi, v[12], v[13]);
                    boolean now = wcv.violation(so, vo, si, vi);
                    boolean within = wcv.conflict(so, vo, si, vi, v[12], v[13]);
                    writer.println(id + "," + cd.time_in + "," + cd.time_out + ","
                            + flag(cd.conflict()) + "," + flag(now) + "," + flag(within) + ",");
                } catch (Throwable e) { // Any failure of the original is recorded, not fatal.
                    writer.println(id + ",,,,,," + e.getClass().getSimpleName());
                }
            }
        }
    }

    static void bench(String input, int passes) throws IOException {
        Table table = load(input);
        // Only vectors in the domain (the same filter that the Rust benchmark applies).
        List<double[]> valid = new ArrayList<>();
        for (String[] row : table.rows()) {
            double[] v = values(table, row);
            boolean ok = true;
            for (double x : v) {
                ok &= Double.isFinite(x);
            }
            ok &= v[14] > 0 && v[15] > 0 && v[16] >= 0 && v[17] >= 0 && 0 <= v[12] && v[12] < v[13];
            if (ok) {
                valid.add(v);
            }
        }
        int n = valid.size();
        WCV_TAUMOD[] detectors = new WCV_TAUMOD[n];
        Vect3[][] states = new Vect3[n][];
        double[] b = new double[n];
        double[] t = new double[n];
        Map<String, WCV_TAUMOD> cache = new HashMap<>();
        for (int i = 0; i < n; i++) {
            double[] v = valid.get(i);
            String key = v[14] + "/" + v[15] + "/" + v[16] + "/" + v[17];
            detectors[i] = cache.computeIfAbsent(key, k -> detector(v));
            states[i] = new Vect3[] {
                new Vect3(v[0], v[1], v[2]), new Vect3(v[3], v[4], v[5]),
                new Vect3(v[6], v[7], v[8]), new Vect3(v[9], v[10], v[11])
            };
            b[i] = v[12];
            t[i] = v[13];
        }
        com.sun.management.ThreadMXBean threads =
                (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
        long thread = Thread.currentThread().threadId();
        for (String kind : new String[] {"detect", "violation"}) {
            double[] times = new double[passes];
            long bytes = 0;
            double total = 0;
            for (int pass = -10; pass < passes; pass++) { // Ten warm-up passes.
                long allocated = threads.getThreadAllocatedBytes(thread);
                long start = System.nanoTime();
                if (kind.equals("detect")) {
                    for (int i = 0; i < n; i++) {
                        Vect3[] q = states[i];
                        ConflictData cd = detectors[i].conflictDetection(q[0], q[1], q[2], q[3], b[i], t[i]);
                        total += cd.time_out;
                    }
                } else {
                    for (int i = 0; i < n; i++) {
                        Vect3[] q = states[i];
                        if (detectors[i].violation(q[0], q[1], q[2], q[3])) {
                            total += 1;
                        }
                    }
                }
                long end = System.nanoTime();
                if (pass >= 0) {
                    times[pass] = (end - start) / (double) n;
                    bytes = threads.getThreadAllocatedBytes(thread) - allocated;
                }
            }
            sink = total;
            Arrays.sort(times);
            System.out.printf(Locale.ROOT,
                    "%s n=%d passes=%d ns_per_call_median=%.2f ns_per_call_min=%.2f bytes_per_call=%.1f%n",
                    kind, n, passes, times[passes / 2], times[0], bytes / (double) n);
        }
    }
}
