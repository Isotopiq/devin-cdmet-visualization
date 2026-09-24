import { useState } from 'react'
import { LuHelpCircle, LuChevronDown, LuChevronRight } from 'react-icons/lu'

interface HelpEntry {
  key: string
  title: string
  what: string
  how: string[]
  options: string[]
  tips?: string[]
}

const SECTIONS: { title: string; entries: HelpEntry[] }[] = [
  {
    title: 'Multivariate overview',
    entries: [
      {
        key: 'pca',
        title: 'PCA',
        what: 'Unsupervised overview of sample-to-sample similarity. Samples that cluster together have similar overall lipid profiles.',
        how: [
          'Each feature is standardized (mean 0, SD 1) across the included samples.',
          'Principal components are the orthogonal directions of maximum variance; PC1 explains the most, PC2 the next most.',
          'The % variance shown on each axis is the fraction of total variance captured by that component.',
          'Confidence ellipses (when shown) are the 95% region for each group in score space.',
        ],
        options: [
          'Include groups: toggle which sample groups are projected. Blank/QC/pool groups are unchecked by default.',
          'Excluded samples are removed before scaling.',
        ],
        tips: ['PCA does not use group labels, so separation in PCA is stronger evidence than in PLS-DA.'],
      },
      {
        key: 'pls_da',
        title: 'PLS-DA',
        what: 'Supervised projection that finds components maximizing separation between Group A and Group B.',
        how: [
          'Partial least squares regression of standardized intensities on a 0/1 group vector.',
          'Scores plot: samples in latent-variable space. Loadings/VIP: features driving the separation (VIP > 1 is the usual cutoff).',
          'R2X / R2Y: variance in X / Y explained. Q2Y: cross-validated predictive ability (k-fold). Values near 0 or negative mean the model does not generalize.',
          'Permutation test: group labels are shuffled 100 times and the model refit; the p-value is the fraction of permuted models that perform as well as the real one.',
        ],
        options: ['Group A and Group B: the two classes being discriminated.'],
        tips: ['PLS-DA overfits easily with small n. Trust Q2Y and the permutation p-value, not the scores plot alone.'],
      },
      {
        key: 'opls_da',
        title: 'OPLS-DA',
        what: 'Variant of PLS-DA with one predictive component and orthogonal components that absorb variation unrelated to group.',
        how: [
          'The predictive component (x-axis) carries all between-group variation; orthogonal components (y-axis) carry within-group variation.',
          'S-plot: covariance (p) vs correlation (p(corr)) of each feature with the predictive score; features in the far corners are strong, reliable discriminators.',
          'Model quality (R2, Q2, permutation p) is computed as in PLS-DA.',
        ],
        options: ['Group A and Group B.'],
      },
      {
        key: 'permanova',
        title: 'PERMANOVA',
        what: 'Non-parametric test of whether the multivariate centroids of two or more groups differ.',
        how: [
          'Missing/non-positive values are imputed with half the feature minimum, then a Bray-Curtis distance matrix between samples is computed.',
          'A pseudo-F statistic compares between-group to within-group distances.',
          'Group labels are permuted 999 times; the p-value is the fraction of permutations with a pseudo-F at least as large as observed.',
          'R2 is the fraction of total distance variance explained by group.',
        ],
        options: ['Include groups: any two or more groups can be tested at once.'],
        tips: ['A significant PERMANOVA can also reflect unequal dispersion, not only a shift in centroid.'],
      },
      {
        key: 'outlier',
        title: 'Outlier',
        what: 'Flags samples that are far from the rest of their dataset in PCA space.',
        how: [
          'Features with any missing values are dropped, the rest standardized, and a 2-component PCA fitted.',
          'The squared Mahalanobis distance of each sample from the PCA centroid is compared with a chi-square threshold.',
          'Samples exceeding the threshold are labelled as candidate outliers.',
        ],
        options: ['Include groups; excluded samples.'],
        tips: ['Check flagged samples against QC metrics (TIC, missing %) before removing them.'],
      },
    ],
  },
  {
    title: 'Differential analysis',
    entries: [
      {
        key: 'volcano',
        title: 'Volcano',
        what: 'Shows every feature by effect size (log2 fold change, x) and significance (-log10 adjusted p, y) for Group B vs Group A.',
        how: [
          'log2FC = log2(mean B / mean A) on the stored (preprocessed) intensities.',
          'A per-feature two-group test produces a p-value; the multiple-testing method converts these to adjusted p-values (padj).',
          'Points with |log2FC| >= the FC cutoff and padj < the p-value cutoff are coloured up (right) or down (left).',
          'Label top N labels the N most significant coloured points.',
        ],
        options: [
          'Test: Welch t-test (default; does not assume equal variances), Student t-test (equal variances), Mann-Whitney U (rank-based, non-parametric), Paired t-test and Wilcoxon signed-rank (for matched samples; require equal n in both groups).',
          'Multiple testing: Benjamini-Hochberg FDR (default), Bonferroni, Holm, or None. The y-axis and cutoff always use the adjusted value.',
          'log2FC cutoff and p-value cutoff draw the dashed threshold lines.',
        ],
        tips: ['Use Mann-Whitney for very skewed data; with fewer than about 5 samples per group it cannot reach small p-values.'],
      },
      {
        key: 'per_lipid_bars',
        title: 'Per-lipid bars',
        what: 'Bar charts of group means for the most significant individual features.',
        how: [
          'A statistical test is run across the included groups (two-group tests for two groups, ANOVA/Kruskal-Wallis for more).',
          'Features are ranked by adjusted p-value and the top N are drawn as one bar per group with error bars (SEM).',
        ],
        options: ['Test: same list as Volcano plus ANOVA and Kruskal-Wallis for three or more groups.', 'Top N / all lipids; include groups.'],
      },
      {
        key: 'biomarker',
        title: 'Biomarkers',
        what: 'Ranks features by how well each one alone separates Group B from Group A, and fits a Random Forest using all features together.',
        how: [
          'Top candidate AUC: for each feature, the area under the ROC curve using the raw intensity as the classifier score (0.5 = no separation, 1 = perfect). Bars are coloured by direction: the Group B colour when the feature is higher in Group B (log2FC > 0), the Group A colour when higher in Group A. The legend under the plot shows this mapping.',
          'Candidates are ranked by Mann-Whitney p-value, then by |AUC|.',
          'Random Forest ROC: a 200-tree Random Forest is fit to all features; the ROC curve and AUC/accuracy are from cross-validated predictions.',
          'Top RF importances: mean decrease in impurity for each feature in the forest (green bars; not group-specific).',
          "Table: AUC, p-value, adjusted p (FDR), Cohen's d (standardized mean difference) and post-hoc power at alpha = 0.05.",
        ],
        options: ['Group A / Group B per comparison. Add comparison, All pairwise, or Each vs a reference group produce one panel per comparison.'],
        tips: ['A high single-feature AUC with small n is fragile; prefer candidates that also appear in the RF importances.'],
      },
    ],
  },
  {
    title: 'Composition and structure',
    entries: [
      {
        key: 'heatmap',
        title: 'Heatmap',
        what: 'Matrix of feature intensities (rows) across samples (columns), optionally clustered.',
        how: [
          'Abundance: the top N most variable features are selected, then scaled per row (row z-score, log10, or none).',
          'Correlation: Pearson correlation between samples (sample x sample).',
          'Hierarchical clustering uses the selected distance metric (e.g. Euclidean, correlation) and linkage method (average, complete, ward, ...). Dendrograms show the merge order.',
        ],
        options: ['Type, Style (Default, Publication, LipidOne, Seaborn, Matplotlib), Top N, Scale, Metric, Method, cluster rows/columns, colour scale, title.'],
      },
      {
        key: 'lipid_classes',
        title: 'Lipid classes',
        what: 'Total intensity per lipid class, compared between groups.',
        how: [
          'The class is parsed from each lipid name (e.g. PC, PE, TG) or taken from feature metadata.',
          'Intensities of all lipids in a class are summed per sample, then averaged per group; error bars are SEM.',
        ],
        options: ['Select which classes to display; include groups.'],
      },
      {
        key: 'chain_space',
        title: 'Chain space',
        what: 'Maps fold change onto acyl-chain structure: carbon number (x) vs number of double bonds (y).',
        how: [
          'Chain composition is parsed from lipid names and building-block totals are summed per sample.',
          'Each bubble is a (carbons, double bonds) block; colour is log2FC (B vs A), size scales with total intensity, and the adjusted p-value is shown on hover.',
        ],
        options: ['Group A / Group B.'],
      },
      {
        key: 'functional',
        title: 'Functional',
        what: 'Volcano-style plot of derived lipid indices (e.g. saturation, unsaturation, class ratios) between two groups.',
        how: [
          'Class totals and saturated/unsaturated fractions are computed per sample, then combined into published functional indices.',
          'Each index is compared between Group A and Group B (log2FC and p-value), and plotted like a volcano.',
        ],
        options: ['Group A / Group B.'],
      },
      {
        key: 'food_profile',
        title: 'Food profile',
        what: 'Nutritional/food-quality lipid indices (e.g. PUFA/SFA, n-3/n-6 style ratios) compared between two groups.',
        how: ['Same pipeline as Functional, using the food-profile index set.'],
        options: ['Group A / Group B.'],
      },
    ],
  },
  {
    title: 'Quality control',
    entries: [
      {
        key: 'qc',
        title: 'QC page',
        what: 'Per-sample and per-group quality metrics to spot bad injections, drift, and blanks.',
        how: [
          'TIC: sum of all feature intensities per sample.',
          'Missing %: fraction of features that are NaN/zero per sample.',
          'Detected features: count of non-missing features per sample.',
          'log2 intensity distribution: box plot per sample of log2 intensities.',
          'CV by group: coefficient of variation (SD / mean) of each feature within a group, summarized per group; pooled QC groups should have low CV.',
          'PCA and sample correlation heatmap as in Visualize.',
        ],
        options: ['Include groups and group display order, x-axis label and axis-title font sizes, which plots to include in the PDF.', 'The QC PDF embeds the exact Plotly images rendered in your browser.'],
      },
    ],
  },
  {
    title: 'Shared options',
    entries: [
      {
        key: 'groups',
        title: 'Groups and samples',
        what: 'How group selection affects every plot.',
        how: [
          'Group A / Group B define the two-class comparison for Volcano, PLS-DA, OPLS-DA, Biomarkers, Chain space, Functional and Food profile. Fold changes are always B vs A.',
          'Include groups (checkboxes) controls which groups appear in PCA, PERMANOVA, Heatmap, Per-lipid bars, Lipid classes and QC.',
          'Groups whose name looks like a blank, QC, solvent, standard, pool or NTC are unchecked by default.',
          'Excluded samples are removed before any statistic is computed.',
        ],
        options: [],
      },
      {
        key: 'engine',
        title: 'Plotting engine and style',
        what: 'The engine (Plotly or R/ggplot2) decides how a figure is drawn; the style (fonts, colours, palette) decides how it looks. They are independent.',
        how: [
          'Plotly figures are interactive in the browser and can be downloaded as PNG.',
          'R figures are static images rendered server-side with ggplot2.',
        ],
        options: ['Set both under Plot styling; group colours defined there are used consistently across plots and PDF reports.'],
      },
      {
        key: 'pdf',
        title: 'PDF reports',
        what: 'Combines selected sections into one document.',
        how: [
          'Each section is regenerated server-side with the parameters you set in Visualize (test, thresholds, groups, top N).',
          'Volcano uses the Volcano tab test; Per-lipid bars use the Per-lipid test. If they differ, statistics are computed separately for each section.',
        ],
        options: ['Sections, title/subtitle, cover style, group order.'],
      },
    ],
  },
]

function Entry({ entry }: { entry: HelpEntry }) {
  const [open, setOpen] = useState(false)
  return (
    <div id={entry.key} className="border border-slate-200 dark:border-slate-700 rounded-lg">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center justify-between px-4 py-3 text-left">
        <span className="font-semibold text-slate-900 dark:text-white">{entry.title}</span>
        {open ? <LuChevronDown className="text-slate-400" /> : <LuChevronRight className="text-slate-400" />}
      </button>
      {open && (
        <div className="px-4 pb-4 space-y-3 text-sm text-slate-700 dark:text-slate-300">
          <p>{entry.what}</p>
          <div>
            <div className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">How it is calculated</div>
            <ul className="list-disc pl-5 space-y-1">{entry.how.map((h, i) => <li key={i}>{h}</li>)}</ul>
          </div>
          {entry.options.length > 0 && (
            <div>
              <div className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Options</div>
              <ul className="list-disc pl-5 space-y-1">{entry.options.map((o, i) => <li key={i}>{o}</li>)}</ul>
            </div>
          )}
          {entry.tips && entry.tips.length > 0 && (
            <div>
              <div className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 mb-1">Tips</div>
              <ul className="list-disc pl-5 space-y-1">{entry.tips.map((t, i) => <li key={i}>{t}</li>)}</ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function Help() {
  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="page-title flex items-center gap-2"><LuHelpCircle /> Help &amp; methods</h1>
        <p className="page-subtitle">How each visualization is calculated and what its options do. Click a heading to expand it.</p>
      </div>
      <div className="card p-4 text-sm text-slate-600 dark:text-slate-400 flex flex-wrap gap-2">
        {SECTIONS.flatMap(s => s.entries).map(e => (
          <a key={e.key} href={`#${e.key}`} className="px-2 py-1 rounded-md bg-slate-100 dark:bg-slate-700 hover:bg-indigo-100 dark:hover:bg-indigo-900">{e.title}</a>
        ))}
      </div>
      {SECTIONS.map(section => (
        <div key={section.title} className="card p-5 space-y-3">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-white">{section.title}</h2>
          {section.entries.map(e => <Entry key={e.key} entry={e} />)}
        </div>
      ))}
    </div>
  )
}
