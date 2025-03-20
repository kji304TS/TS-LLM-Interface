import pandas as pd
import glob
from collections import Counter
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.cluster import KMeans
from textblob import TextBlob
import matplotlib.pyplot as plt
import seaborn as sns

# Step 1: Load and Merge All Files


file_path_pattern = r"C:\Users\kji30\OneDrive\Desktop\LLM project\final-scripts\Jan 2025\*.csv"

# Get all matching CSV files
files = glob.glob(file_path_pattern)

if not files:
    print("⚠️ No CSV files found! Double-check the folder path and ensure files have a .csv extension.")
else:
    print(f"✅ Found {len(files)} CSV files:")
    for file in files:
        print(file)  # Print each file name


# Use the correct file path
file_path_pattern = r"C:\Users\kji30\OneDrive\Desktop\LLM project\final-scripts\Jan 2025\*.csv"
data = load_and_merge_files(file_path_pattern)
print("✅ All files loaded successfully.")

# Step 2: Filter Conversations by Category
def filter_by_category(df, category):
    return df[df["MM Card Partner issue"] == category].dropna()

# Step 3: Extract Common Phrases
def extract_phrases(text_list, ngram_range=(2, 3), top_n=10):
    vectorizer = CountVectorizer(ngram_range=ngram_range, stop_words='english')
    X = vectorizer.fit_transform(text_list)
    phrase_counts = X.toarray().sum(axis=0)
    phrases = [(phrase, phrase_counts[idx]) for phrase, idx in vectorizer.vocabulary_.items()]
    return sorted(phrases, key=lambda x: x[1], reverse=True)[:top_n]

# Step 4: Perform Sentiment Analysis
def get_sentiment(text):
    return TextBlob(text).sentiment.polarity

def analyze_sentiment(df):
    df["Sentiment"] = df["transcript"].apply(lambda x: get_sentiment(str(x)))
    return df

# Step 5: Identify Unresolved Issues
def find_unresolved_issues(df):
    return df[df["summary"].str.contains("not resolved|issue persists|still having trouble", case=False, na=False)]

# Step 6: Detect Trends Over Time
def analyze_trends(df):
    if "conversation_id" in df.columns:
        return df.groupby("conversation_id").size().reset_index(name="Count")
    return None

# Step 7: Cluster Conversations
def cluster_conversations(df, num_clusters=3):
    text_data = df["transcript"].dropna().tolist()
    if text_data:
        vectorizer = TfidfVectorizer(stop_words="english", max_features=1000)
        X = vectorizer.fit_transform(text_data)
        kmeans = KMeans(n_clusters=num_clusters, random_state=42, n_init=10)
        df.loc[df["transcript"].notna(), "Cluster"] = kmeans.fit_predict(X)
    return df

# Step 8: Export Results to Excel
def export_to_excel(df, category):
    file_name = f"{category}_Analysis_Report.xlsx"
    df.to_excel(file_name, index=False)
    print(f"📂 Report saved: {file_name}")

# Step 9: Generate Final Reports
def generate_reports(df, category):
    print(f"\n📊 Report for {category} Issues:")
    print("Most Common Phrases:")
    print(pd.DataFrame(extract_phrases(df["transcript"].dropna().tolist()), columns=["Phrase", "Frequency"]))
    
    print("\n📈 Sentiment Analysis:")
    sentiment_summary = df.groupby("MM Card Partner issue")["Sentiment"].mean().reset_index()
    print(sentiment_summary)
    
    print("\n⚠️ Unresolved Issues:")
    print(find_unresolved_issues(df))
    
    print("\n📅 Trends Over Time:")
    trends = analyze_trends(df)
    if trends is not None:
        print(trends)
    
    print("\n🔍 Clustered Conversations:")
    clustered_df = cluster_conversations(df)
    print(clustered_df[["conversation_id", "MM Card Partner issue", "summary", "Cluster"]])
    
    # Plot sentiment distribution
    plt.figure(figsize=(10, 5))
    sns.boxplot(x=clustered_df["Cluster"], y=clustered_df["Sentiment"])
    plt.title(f"Sentiment Scores by Cluster for {category} Issues")
    plt.xlabel("Cluster")
    plt.ylabel("Sentiment Score")
    plt.show()
    
    # Export results to Excel
    export_to_excel(clustered_df, category)

# Main Execution
if __name__ == "__main__":
    # Define the correct file path pattern
    file_path_pattern = r"C:\\Users\\kji30\\OneDrive\\Desktop\\LLM project\\final-scripts\\Jan 2025\\*.csv"
    
    # Load all files
    data = load_and_merge_files(file_path_pattern)
    
    # Process each category
    for category in ["KYC Issue", "Dashboard Issue", "Other"]:
        df_category = filter_by_category(data, category)
        df_category = analyze_sentiment(df_category)
        generate_reports(df_category, category)
