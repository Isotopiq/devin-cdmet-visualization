import json
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from app import models, schemas
from app.services.preprocessing import to_dataframe


def generate_plot(dataset: models.Dataset, req: schemas.PlotRequest):
    df = to_dataframe(dataset)
    sample_meta = dataset.sample_metadata
    plot_type = req.plot_type

    if plot_type == "box":
        fig = go.Figure()
        for sample, group in sample_meta.items():
            if sample in df.columns:
                fig.add_trace(go.Box(y=df[sample].values, name=f"{group}:{sample}"))
        fig.update_layout(title="Sample Box Plot", xaxis_title="Sample", yaxis_title="Abundance")

    elif plot_type == "heatmap":
        corr = df.corr()
        fig = px.imshow(corr, text_auto=True, aspect="auto", title="Correlation Heatmap")

    elif plot_type == "pca":
        X = df.dropna().T
        X = X.fillna(X.min().min() / 2)
        scaler = StandardScaler()
        Xs = scaler.fit_transform(X)
        pca = PCA(n_components=min(3, len(X)))
        scores = pca.fit_transform(Xs)
        labels = [sample_meta.get(c, c) for c in df.columns]
        fig = px.scatter(x=scores[:, 0], y=scores[:, 1], color=labels,
                         labels={"x": f"PC1 ({pca.explained_variance_ratio_[0]*100:.1f}%)",
                                 "y": f"PC2 ({pca.explained_variance_ratio_[1]*100:.1f}%)"},
                         title="PCA Score Plot")

    elif plot_type == "volcano":
        stats = req.parameters.get("stats", [])
        fc = [s["log2fc"] for s in stats if s.get("log2fc") is not None]
        p = [-np.log10(s["padj"]) for s in stats if s.get("padj") is not None]
        names = [s["feature_id"] for s in stats]
        fig = px.scatter(x=fc, y=p, hover_name=names,
                         labels={"x": "log2 Fold Change", "y": "-log10 adjusted p-value"},
                         title="Volcano Plot")

    elif plot_type == "bar":
        feature = req.parameters.get("feature", 0)
        values = df.iloc[feature].values
        samples = df.columns
        groups = [sample_meta.get(c, "unknown") for c in samples]
        fig = px.bar(x=samples, y=values, color=groups,
                     labels={"x": "Sample", "y": "Abundance"},
                     title=f"Abundance: {dataset.feature_metadata[feature].get('feature_id', feature)}")

    elif plot_type == "rt_mz":
        mz = [float(f.get("mz", 0) or 0) for f in dataset.feature_metadata]
        rt = [float(f.get("rt", 0) or 0) for f in dataset.feature_metadata]
        grades = [f.get("grade", "unknown") for f in dataset.feature_metadata]
        fig = px.scatter(x=mz, y=rt, color=grades,
                         labels={"x": "m/z", "y": "Retention Time"},
                         title="Retention Time vs m/z")

    else:
        fig = go.Figure()
        fig.update_layout(title="Unsupported plot type")

    return json.loads(fig.to_json())
