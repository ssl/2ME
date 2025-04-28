# process_tlds.py

def process_tlds(input_file: str, output_file: str) -> None:
    """
    Reads TLDs from the input_file, processes each by
    converting to lowercase and prefixing with 'mail.',
    then writes the results to the output_file.
    
    Args:
        input_file (str): Path to the input file containing TLDs.
        output_file (str): Path to the output file to write processed TLDs.
    """
    try:
        with open(input_file, 'r', encoding='utf-8') as infile:
            # Read all lines from the input file
            lines = infile.readlines()
        
        processed_lines = []
        for line in lines:
            # Strip leading/trailing whitespace and newline characters
            tld = line.strip()
            if not tld:
                # Skip empty lines
                continue

            if len(tld) > 3:
                # Skip TLDs
                continue
            
            # Ensure the TLD starts with a dot
            if not tld.startswith('.'):
                tld = f'.{tld}'
            
            # Convert to lowercase and prefix with 'mail.'
            processed_tld = f'cloud{tld.lower()}'
            processed_lines.append(processed_tld)
        
        # Write the processed TLDs to the output file
        with open(output_file, 'w', encoding='utf-8') as outfile:
            for processed_line in processed_lines:
                outfile.write(processed_line + '\n')
        
        print(f"Processed {len(processed_lines)} TLDs and wrote to '{output_file}'.")
    
    except FileNotFoundError:
        print(f"Error: The file '{input_file}' does not exist.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    # Define input and output file paths
    input_filename = 'all-tlds.txt'
    output_filename = 'checkthis.txt'
    
    # Process the TLDs
    process_tlds(input_filename, output_filename)
