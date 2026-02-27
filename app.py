import os
import re
import tempfile
from flask import Flask, render_template, request, flash

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change for production

# ---------- Validation Logic ----------
def parse_numbers(cell):
    """Convert a string like '15,2,7,14,11' into a list of ints."""
    if not cell or cell.strip() == '':
        return []
    parts = re.split(r'[,\s]+', cell.strip())
    numbers = []
    for p in parts:
        if p == '':
            continue
        try:
            numbers.append(int(p))
        except ValueError:
            numbers.append(None)  # Mark invalid
    return numbers

def validate_card(card_id, b_numbers, i_numbers, n_numbers, g_numbers, o_numbers):
    """
    Validate one card.
    Returns (is_valid, message).
    """
    columns = [
        ('B', b_numbers, (1,15)),
        ('I', i_numbers, (16,30)),
        ('N', n_numbers, (31,45)),
        ('G', g_numbers, (46,60)),
        ('O', o_numbers, (61,75))
    ]
    errors = []

    for col_name, numbers, (low, high) in columns:
        if len(numbers) != 5:
            errors.append(f"{col_name}: expected 5 numbers, got {len(numbers)}")
            continue

        seen = set()
        for pos, num in enumerate(numbers):
            if num is None:
                errors.append(f"{col_name}: non‑numeric value")
                continue
            # Free space: N column, third position
            if col_name == 'N' and pos == 2:
                if num != 0:
                    errors.append(f"{col_name} center should be 0, got {num}")
                continue
            if not (low <= num <= high):
                errors.append(f"{col_name}: {num} out of range ({low}-{high})")
            if num in seen:
                errors.append(f"{col_name}: duplicate number {num}")
            seen.add(num)

    if errors:
        return False, f"Card {card_id}: " + "; ".join(errors)
    return True, f"Card {card_id}: Valid"

def parse_text_table(text):
    """
    Parse the text table into a list of cards.
    Returns list of tuples (card_id, b_list, i_list, n_list, g_list, o_list).
    """
    lines = text.strip().splitlines()
    data_lines = []
    header_found = False

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Detect header line starting with "card" (case‑insensitive)
        if re.match(r'^card\s', line, re.IGNORECASE):
            header_found = True
            continue

        if header_found:
            parts = re.split(r'\s+', line)
            if len(parts) < 6:
                continue  # skip malformed lines

            card_id = parts[0]
            b_str = parts[1]
            i_str = parts[2]
            n_str = parts[3]
            g_str = parts[4]
            o_str = parts[5]

            b_nums = parse_numbers(b_str)
            i_nums = parse_numbers(i_str)
            n_nums = parse_numbers(n_str)
            g_nums = parse_numbers(g_str)
            o_nums = parse_numbers(o_str)

            data_lines.append((card_id, b_nums, i_nums, n_nums, g_nums, o_nums))

    return data_lines
# ---------------------------------------

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/validate', methods=['POST'])
def validate():
    # Get input from textarea or uploaded file
    text_data = None
    if 'text_input' in request.form and request.form['text_input'].strip():
        text_data = request.form['text_input']
    elif 'file' in request.files:
        uploaded_file = request.files['file']
        if uploaded_file.filename != '':
            # For simplicity, assume it's a text file
            text_data = uploaded_file.read().decode('utf-8')
        else:
            flash('No file selected.')
            return render_template('index.html')
    else:
        flash('Please paste data or upload a file.')
        return render_template('index.html')

    # Parse cards
    cards = parse_text_table(text_data)
    if not cards:
        flash('No valid card data found. Check that the header line starts with "card".')
        return render_template('index.html')

    # First, run per-card validation and store results
    card_results = []  # list of (card_id, b, i, n, g, o, is_valid, message)
    for card in cards:
        card_id, b, i, n, g, o = card
        valid, msg = validate_card(card_id, b, i, n, g, o)
        card_results.append((card_id, b, i, n, g, o, valid, msg))

    # Build fingerprints for duplicate detection
    fingerprint_map = {}
    for idx, (card_id, b, i, n, g, o, valid, msg) in enumerate(card_results):
        # Use tuple of tuples as fingerprint (order matters)
        fingerprint = (tuple(b), tuple(i), tuple(n), tuple(g), tuple(o))
        fingerprint_map.setdefault(fingerprint, []).append((card_id, idx))

    # Mark duplicates
    duplicate_groups = []
    for fingerprint, id_list in fingerprint_map.items():
        if len(id_list) > 1:
            duplicate_groups.append([card_id for card_id, _ in id_list])
            # Mark each card in this group as invalid (if not already)
            for card_id, idx in id_list:
                other_ids = [cid for cid, _ in id_list if cid != card_id]
                duplicate_msg = f"Duplicate of card(s) {', '.join(other_ids)}"
                # Update the card's result
                card_id, b, i, n, g, o, old_valid, old_msg = card_results[idx]
                if old_valid:
                    # If it was valid before, now invalid due to duplicate
                    card_results[idx] = (card_id, b, i, n, g, o, False, f"Valid but {duplicate_msg}")
                else:
                    # Append duplicate info to existing error message
                    card_results[idx] = (card_id, b, i, n, g, o, False, old_msg + f"; {duplicate_msg}")

    # Separate valid and invalid for display
    valid_msgs = [msg for _, _, _, _, _, _, valid, msg in card_results if valid]
    invalid_msgs = [msg for _, _, _, _, _, _, valid, msg in card_results if not valid]

    return render_template('index.html',
                           invalid_msgs=invalid_msgs,
                           valid_count=len(valid_msgs),
                           duplicate_groups=duplicate_groups,
                           original_text=text_data)

if __name__ == '__main__':
    app.run(debug=True)