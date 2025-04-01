# Scan Namer Agent

Automatically renames scanned documents from Microsoft Lens (or similar apps) based on their content using AI.

## How It Works

The agent monitors a specified folder for files with default Microsoft Lens naming patterns (e.g., `3_28_25, 12_51 PM Microsoft Lens.jpg`). When it finds such files, it analyzes their content using OpenAI's vision model (GPT-4o mini) and renames them to something more descriptive based on what's in the document.


## Features

- Automatically detects new scans with default naming
- Uses AI to analyze document content and generate meaningful filenames
- Identifies multi-page documents and names them accordingly (e.g., `Invoice_ABC_Company_page_01.jpg`)
- Handles JPEG/JPG, PNG, and PDF files
- Preserves original file extensions
- Handles filename conflicts elegantly
- Can run once or as a continuous monitoring agent
- Logs all activity for troubleshooting

## Setup

### Automated Setup (Recommended)

1. Run the setup script which will handle most of the setup steps:
   ```
   python setup.py
   ```
2. Edit the created `.env` file with your OpenAI API key and folder path
3. Run the agent

### Manual Setup

If the automated setup doesn't work, follow these steps:

1. Install Python 3.8+ if you don't already have it
2. Create a virtual environment (recommended):
   ```
   python -m venv venv
   
   # On Windows
   venv\Scripts\activate
   
   # On macOS/Linux
   source venv/bin/activate
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Create a `.env` file with the following content:
   ```
   OPENAI_API_KEY="your_openai_api_key_here"
   SCAN_FOLDER_PATH="C:/Users/username/Path/To/Your/Scan/Folder/"
   CHECK_INTERVAL=60
   CONTINUOUS_MONITORING=False
   ```
5. Replace the placeholder values with your actual settings

### Simple Install (Alternative)

If you're having trouble with virtual environments:

1. Install the required packages directly:
   ```
   pip install openai python-dotenv pillow watchdog
   ```

2. Create a `.env` file in the same folder as the script with:
   ```
   OPENAI_API_KEY="your_openai_api_key_here"
   SCAN_FOLDER_PATH="C:/Users/username/Path/To/Your/Scan/Folder/"
   CHECK_INTERVAL=60
   CONTINUOUS_MONITORING=False
   ```

3. Run the agent:
   ```
   python scan_agent.py
   ```
   
## Scanning Setup

### Microsoft Lens Setup (Recommended)

1. Install Microsoft Lens:
   - [Android - Google Play Store](https://play.google.com/store/apps/details?id=com.microsoft.office.officelens)
   - [iOS - App Store](https://apps.apple.com/us/app/microsoft-lens-pdf-scanner/id975925059)

2. Configure OneDrive sync:
   - Open Microsoft Lens
   - Sign in with your Microsoft account
   - Go to Settings > Cloud Storage
   - Enable OneDrive sync
   - Choose or create a folder for your scans (remember this path for later)

3. Scanning Best Practices:
   - Use good lighting
   - Keep the camera steady
   - Ensure the document is flat and fully visible
   - For multi-page documents, use the "Add New" button between pages
   - Choose "Document" mode for text documents
   - Use "Photo" mode for images or colorful content
   - Use "Whiteboard" mode for whiteboards or flipcharts

### Alternative Scanning Apps

You can use any scanning app that saves to a monitored folder. Some alternatives:
- Adobe Scan
- Scanner Pro
- Your phone's built-in document scanner

### OneDrive Setup

1. Install OneDrive on your computer:
   - [Download OneDrive](https://www.microsoft.com/en-us/microsoft-365/onedrive/download)
2. Sign in with the same Microsoft account used in Microsoft Lens
3. Ensure the scan folder is synced to your computer
4. Use this local sync folder path in your `.env` configuration

## Getting an OpenAI API Key

1. Visit [OpenAI's Platform website](https://platform.openai.com/)
2. Click "Sign Up" or "Log In"
3. Go to [API Keys section](https://platform.openai.com/api-keys)
4. Click "Create new secret key"
5. Copy the key (you won't be able to see it again!)
6. Add the key to your `.env` file

Note: OpenAI API usage is not free, but the cost for renaming documents is typically very low (a few cents or less per document).

## Usage

### One-time Processing

To scan and process all files in the folder once:

```
python scan_agent.py
```

To reprocess all files, even if they've been processed before:

```
python scan_agent.py --force
```

### Continuous Monitoring

To continuously monitor for new files, set `CONTINUOUS_MONITORING=True` in your `.env` file, then run:

```
python scan_agent.py
```

Or use the command line flag to override the setting in the `.env` file:

```
python scan_agent.py --continuous
```

### Command Line Options

The following command line options are available:

- `--force`, `-f`: Force reprocessing of all matching files, even if they've been processed before
- `--continuous`, `-c`: Run in continuous monitoring mode (overrides .env setting)
- `--once`, `-o`: Run once and exit (overrides .env setting)

### Multi-page Documents

#### Image Files (JPG, JPEG, PNG)

The agent automatically detects when multiple image files are scanned in sequence (within 60 seconds of each other) and treats them as pages of the same document. The images will be renamed with a consistent base name plus page numbers:

For example, if you scan multiple pages of an invoice as separate image files, they will be renamed to:
- `Invoice_ABC_Company_page_01.jpg`
- `Invoice_ABC_Company_page_02.jpg`
- etc.

Only files with the same extension (all JPGs or all PNGs) will be grouped together.

#### PDF Files

PDFs are always treated as standalone documents, since they can already contain multiple pages. Each PDF is analyzed and renamed individually based on its content, regardless of when it was created.

For PDFs, the agent converts only the first page to an image for analysis by the AI model, then uses the resulting name suggestion for the entire PDF file.

## Configuration

Edit the `.env` file to configure:

- `OPENAI_API_KEY`: Your OpenAI API key
- `SCAN_FOLDER_PATH`: Path to the folder containing your scans (use forward slashes)
- `CHECK_INTERVAL`: How often to check for new files (in seconds) when in continuous mode
- `CONTINUOUS_MONITORING`: Set to `True` to run continuously, `False` for one-time run

## Requirements

- Python 3.8+
- OpenAI API key
- Dependencies listed in `requirements.txt`

### PDF Support Requirements

To enable PDF processing, you also need Poppler:

- **Windows:** Download from [here](https://github.com/oschwartz10612/poppler-windows/releases/) and add the `bin` folder to your PATH
- **Mac:** `brew install poppler`
- **Linux:** `apt-get install poppler-utils`

PDF processing converts the first page of each PDF to an image before sending to the OpenAI API. 