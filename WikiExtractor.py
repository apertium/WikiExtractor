#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Incubator module added by Grzegorz Stark for Apertium, in December 2017.
#
# And changed even more by Ben Stobaugh for Apertium, in December 2013.
#
# Hacked up by Alex Rudnick for use in Guampa, October 2013.
#
# =============================================================================
#  Version: 2.5 (May 9, 2013)
#  Author: Giuseppe Attardi (attardi@di.unipi.it), University of Pisa
#      Antonio Fuschetto (fuschett@di.unipi.it), University of Pisa
#
#  Contributors:
#   Leonardo Souza (lsouza@amtera.com.br)
#   Juan Manuel Caicedo (juan@cavorite.com)
#   Humberto Pereira (begini@gmail.com)
#   Siegfried-A. Gevatter (siegfried@gevatter.com)
#   Pedro Assis (pedroh2306@gmail.com)
#
# =============================================================================
#  Copyright (c) 2009. Giuseppe Attardi (attardi@di.unipi.it).
# =============================================================================
#  This file is part of Tanl.
#
#  Tanl is free software; you can redistribute it and/or modify it
#  under the terms of the GNU General Public License, version 3,
#  as published by the Free Software Foundation.
#
#  Tanl is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS f A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.
# =============================================================================

"""Wikipedia Extractor:
Extracts and cleans text from Wikipedia database dump and stores output in a
number of files of similar size in a given directory.
Each file contains several documents in Tanl document format:
    <doc id="" url="" title="">
        ...
        </doc>

Usage:
  WikiExtractor.py [options]
"""

import argparse
import gc
import sys
import urllib.request
import re
import bz2
import os.path
from html.entities import name2codepoint
import shutil
import mimetypes
import gzip


#import nltk
## NOTE: This is customizable. Your source data may not be in English
#SEGMENTER = nltk.data.load("nltk:tokenizers/punkt/english.pickle")

### PARAMS ####################################################################

# This is obtained from the dump itself
PREFIX = None

##
# Whether to preseve links in output
#
keepLinks = False

##
# Whether to transform sections into HTML
#
keepSections = False

##
# Recognize only these namespaces
# w: Internal links to the Wikipedia
#
ACCEPTED_NAMESPACES= set(['w'])

##
# Drop these elements from article text
#
DISCARD_ELEMENTS = set([
        'gallery', 'timeline', 'noinclude', 'pre',
        'table', 'tr', 'td', 'th', 'caption',
        'form', 'input', 'select', 'option', 'textarea',
        'ul', 'li', 'ol', 'dl', 'dt', 'dd', 'menu', 'dir',
        'ref', 'references', 'img', 'imagemap', 'source'
        ])

#=========================================================================
#
# MediaWiki Markup Grammar
 
# Template = "{{" [ "msg:" | "msgnw:" ] PageName { "|" [ ParameterName "=" AnyText | AnyText ] } "}}" ;
# Extension = "<" ? extension ? ">" AnyText "</" ? extension ? ">" ;
# NoWiki = "<nowiki />" | "<nowiki>" ( InlineText | BlockText ) "</nowiki>" ;
# Parameter = "{{{" ParameterName { Parameter } [ "|" { AnyText | Parameter } ] "}}}" ;
# Comment = "<!--" InlineText "-->" | "<!--" BlockText "//-->" ;
#
# ParameterName = ? uppercase, lowercase, numbers, no spaces, some special chars ? ;
#
#=========================================================================== 

# Program version
version = '2.5'

##### Main function ###########################################################

##def WikiDocument(out, id, title, text):
##    url = get_url(id, prefix)
##    header = '<doc id="%s" url="%s" title="%s">\n' % (id, url, title)
##    # Separate header from text with a newline.
##    header += title + '\n'
##    text = clean(text)
##    footer = "\n</doc>"
##    out.reserve(len(header) + len(text) + len(footer))
##    print(header, file=out)
##    for line in compact(text, structure=True):
##        print(line, file=out)
##    print(footer, file=out)

def WikiDocumentSentences(out, id, title, tags, text):
    url = get_url(id, PREFIX)
    header = '\n{0}:{1}'.format(title, "|||".join(tags))
    # Separate header from text with a newline.
    text = clean(text)

    out.reserve(len(header) + len(text))
    print(header, file=out)
    for line in compact(text, structure=False):
        print(line, file=out)

def get_url(id, prefix):
    return "%s?curid=%s" % (prefix, id)

#------------------------------------------------------------------------------

selfClosingTags = [ 'br', 'hr', 'nobr', 'ref', 'references' ]

# handle 'a' separetely, depending on keepLinks
ignoredTags = [
        'b', 'big', 'blockquote', 'center', 'cite', 'div', 'em',
        'font', 'h1', 'h2', 'h3', 'h4', 'hiero', 'i', 'kbd', 'nowiki',
        'p', 'plaintext', 's', 'small', 'span', 'strike', 'strong',
        'sub', 'sup', 'tt', 'u', 'var',
]

placeholder_tags = {'math':'formula', 'code':'codice'}

### Normalize title
def normalizeTitle(title):
  # remove leading whitespace and underscores
  title = title.strip(' _')
  # replace sequences of whitespace and underscore chars with a single space
  title = re.compile(r'[\s_]+').sub(' ', title)

  m = re.compile(r'([^:]*):(\s*)(\S(?:.*))').match(title)
  if m:
      prefix = m.group(1)
      if m.group(2):
          optionalWhitespace = ' '
      else:
          optionalWhitespace = ''
      rest = m.group(3)

      ns = prefix.capitalize()
      if ns in ACCEPTED_NAMESPACES:
          # If the prefix designates a known namespace, then it might be
          # followed by optional whitespace that should be removed to get
          # the canonical page name
          # (e.g., "Category:  Births" should become "Category:Births").
          title = ns + ":" + rest.capitalize()
      else:
          # No namespace, just capitalize first letter.
      # If the part before the colon is not a known namespace, then we must
          # not remove the space after the colon (if any), e.g.,
          # "3001: The_Final_Odyssey" != "3001:The_Final_Odyssey".
          # However, to get the canonical page name we must contract multiple
          # spaces into one, because
          # "3001:   The_Final_Odyssey" != "3001: The_Final_Odyssey".
          title = prefix.capitalize() + ":" + optionalWhitespace + rest
  else:
      # no namespace, just capitalize first letter
      title = title.capitalize();
  return title

##
# Removes HTML or XML character references and entities from a text string.
#
# @param text The HTML (or XML) source text.
# @return The plain text, as a Unicode string, if necessary.

def unescape(text):
    def fixup(m):
        text = m.group(0)
        code = m.group(1)
        try:
            if text[1] == "#":  # character reference
                if text[2] == "x":
                    return chr(int(code[1:], 16))
                else:
                    return chr(int(code))
            else:               # named entity
                return chr(name2codepoint[code])
        except:
            return text # leave as is

    return re.sub("&#?(\w+);", fixup, text)

# Match HTML comments
comment = re.compile(r'<!--.*?-->', re.DOTALL)

# Match elements to ignore
discard_element_patterns = []
for tag in DISCARD_ELEMENTS:
    pattern = re.compile(r'<\s*%s\b[^>]*>.*?<\s*/\s*%s>' % (tag, tag), re.DOTALL | re.IGNORECASE)
    discard_element_patterns.append(pattern)

# Match ignored tags
ignored_tag_patterns = []
def ignoreTag(tag):
    left = re.compile(r'<\s*%s\b[^>]*>' % tag, re.IGNORECASE)
    right = re.compile(r'<\s*/\s*%s>' % tag, re.IGNORECASE)
    ignored_tag_patterns.append((left, right))

for tag in ignoredTags:
    ignoreTag(tag)

# Match selfClosing HTML tags
selfClosing_tag_patterns = []
for tag in selfClosingTags:
    pattern = re.compile(r'<\s*%s\b[^/]*/\s*>' % tag, re.DOTALL | re.IGNORECASE)
    selfClosing_tag_patterns.append(pattern)

# Match HTML placeholder tags
placeholder_tag_patterns = []
for tag, repl in list(placeholder_tags.items()):
    pattern = re.compile(r'<\s*%s(\s*| [^>]+?)>.*?<\s*/\s*%s\s*>' % (tag, tag), re.DOTALL | re.IGNORECASE)
    placeholder_tag_patterns.append((pattern, repl))

# Match preformatted lines
preformatted = re.compile(r'^ .*?$', re.MULTILINE)

# Match external links (space separates second optional parameter)
externalLink = re.compile(r'\[\w+.*? (.*?)\]')
externalLinkNoAnchor = re.compile(r'\[\w+[&\]]*\]')

# Matches bold/italic
bold_italic = re.compile(r"'''''([^']*?)'''''")
bold = re.compile(r"'''(.*?)'''")
italic_quote = re.compile(r"''\"(.*?)\"''")
italic = re.compile(r"''([^']*)''")
quote_quote = re.compile(r'""(.*?)""')

# Matches space
spaces = re.compile(r' {2,}')

# Matches dots
dots = re.compile(r'\.{4,}')

# A matching function for nested expressions, e.g. namespaces and tables.
def dropNested(text, openDelim, closeDelim):
    openRE = re.compile(openDelim)
    closeRE = re.compile(closeDelim)
    # partition text in separate blocks { } { }
    matches = []                # pairs (s, e) for each partition
    nest = 0                    # nesting level
    start = openRE.search(text, 0)
    if not start:
        return text
    end = closeRE.search(text, start.end())
    next = start
    while end:
        next = openRE.search(text, next.end())
        if not next:            # termination
            while nest:         # close all pending
                nest -=1
                end0 = closeRE.search(text, end.end())
                if end0:
                    end = end0
                else:
                    break
            matches.append((start.start(), end.end()))
            break
        while end.end() < next.start():
            # { } {
            if nest:
                nest -= 1
                # try closing more
                last = end.end()
                end = closeRE.search(text, end.end())
                if not end:     # unbalanced
                    if matches:
                        span = (matches[0][0], last)
                    else:
                        span = (start.start(), last)
                    matches = [span]
                    break
            else:
                matches.append((start.start(), end.end()))
                # advance start, find next close
                start = next
                end = closeRE.search(text, next.end())
                break           # { }
        if next != start:
            # { { }
            nest += 1
    # collect text outside partitions
    res = ''
    start = 0
    for s, e in  matches:
        res += text[start:s]
        start = e
    res += text[start:]
    return res

def dropSpans(matches, text):
    """Drop from text the blocks identified in matches"""
    matches.sort()
    res = ''
    start = 0
    for s, e in  matches:
        res += text[start:s]
        start = e
    res += text[start:]
    return res

# Match interwiki links, | separates parameters.
# First parameter is displayed, also trailing concatenated text included
# in display, e.g. s for plural).
#
# Can be nested [[File:..|..[[..]]..|..]], [[Category:...]], etc.
# We first expand inner ones, than remove enclosing ones.
#
wikiLink = re.compile(r'\[\[([^[]*?)(?:\|([^[]*?))?\]\](\w*)')

parametrizedLink = re.compile(r'\[\[.*?\]\]')

# Function applied to wikiLinks
def make_anchor_tag(match):
    global keepLinks
    link = match.group(1)
    colon = link.find(':')
    if colon > 0 and link[:colon] not in ACCEPTED_NAMESPACES:
        return ''
    trail = match.group(3)
    anchor = match.group(2)
    if not anchor:
        anchor = link
    anchor += trail
    if keepLinks:
        return '<a href="%s">%s</a>' % (link, anchor)
    else:
        return anchor

def clean(text):

    # FIXME: templates should be expanded
    # Drop transclusions (template, parser functions)
    # See: http://www.mediawiki.org/wiki/Help:Templates
    text = dropNested(text, r'{{', r'}}')

    # Drop tables
    text = dropNested(text, r'{\|', r'\|}')

    # Expand links
    text = wikiLink.sub(make_anchor_tag, text)
    # Drop all remaining ones
    text = parametrizedLink.sub('', text)

    # Handle external links
    text = externalLink.sub(r'\1', text)
    text = externalLinkNoAnchor.sub('', text)

    # Handle bold/italic/quote
    text = bold_italic.sub(r'\1', text)
    text = bold.sub(r'\1', text)
    text = italic_quote.sub(r'&quot;\1&quot;', text)
    text = italic.sub(r'&quot;\1&quot;', text)
    text = quote_quote.sub(r'\1', text)
    text = text.replace("'''", '').replace("''", '&quot;')

    ################ Process HTML ###############

    # turn into HTML
    text = unescape(text)
    # do it again (&amp;nbsp;)
    text = unescape(text)

    # Collect spans

    matches = []
    # Drop HTML comments
    for m in comment.finditer(text):
            matches.append((m.start(), m.end()))

    # Drop self-closing tags
    for pattern in selfClosing_tag_patterns:
        for m in pattern.finditer(text):
            matches.append((m.start(), m.end()))

    # Drop ignored tags
    for left, right in ignored_tag_patterns:
        for m in left.finditer(text):
            matches.append((m.start(), m.end()))
        for m in right.finditer(text):
            matches.append((m.start(), m.end()))

    # Bulk remove all spans
    text = dropSpans(matches, text)

    # Cannot use dropSpan on these since they may be nested
    # Drop discarded elements
    for pattern in discard_element_patterns:
        text = pattern.sub('', text)

    # Expand placeholders
    for pattern, placeholder in placeholder_tag_patterns:
        index = 1
        for match in pattern.finditer(text):
            text = text.replace(match.group(), '%s_%d' % (placeholder, index))
            index += 1

    text = text.replace('<<', 'Â«').replace('>>', 'Â»')

    #######################################

    # Drop preformatted
    # This can't be done before since it may remove tags
    text = preformatted.sub('', text)

    # Cleanup text
    text = text.replace('\t', ' ')
    text = spaces.sub(' ', text)
    text = dots.sub('...', text)
    text = re.sub(' (,:\.\)\]Â»)', r'\1', text)
    text = re.sub('(\[\(Â«) ', r'\1', text)
    text = re.sub(r'\n\W+?\n', '\n', text) # lines with only punctuations
    text = text.replace(',,', ',').replace(',.', '.')
    re2 = re.compile(r"__[A-Z]+__")
    text = re2.sub("", text)
    #Add other filters here
    
    return text

section = re.compile(r'(==+)\s*(.*?)\s*\1')

def compact(text, structure=False):
    """Deal with headers, lists, empty sections, residuals of tables"""
    page = []                   # list of paragraph
    headers = {}                # Headers for unfilled sections
    emptySection = False        # empty sections are discarded
    inList = False              # whether opened <UL>

    for line in text.split('\n'):

        if not line:
            continue
        # Handle section titles
        m = section.match(line)
        if m:
            title = m.group(2)
            lev = len(m.group(1))
            if structure:
                page.append("<h%d>%s</h%d>" % (lev, title, lev))
            if title and title[-1] not in '!?':
                title += '.'
            headers[lev] = title
            # drop previous headers
            for i in list(headers.keys()):
                if i > lev:
                    del headers[i]
            emptySection = True
            continue
        # Handle page title
        if line.startswith('++'):
            title = line[2:-2]
            if title:
                if title[-1] not in '!?':
                    title += '.'
                page.append(title)
        # handle lists
        elif line[0] in '*#:;':
            if structure:
                page.append("<li>%s</li>" % line[1:])
            else:
                continue
        # Drop residuals of lists
        elif line[0] in '{|' or line[-1] in '}':
            continue
        # Drop irrelevant lines
        elif (line[0] == '(' and line[-1] == ')') or line.strip('.-') == '':
            continue
        elif len(headers):
            items = list(headers.items())
            items.sort()
            for (i, v) in items:
                page.append(v)
            headers.clear()
            page.append(line)   # first line
            emptySection = False
        elif not emptySection:
            page.append(line)

    return page

def handle_unicode(entity):
    numeric_code = int(entity[2:-1])
    if numeric_code >= 0x10000: return ''
    return chr(numeric_code)

#------------------------------------------------------------------------------

class OutputSplitter:
    def __init__(self, compress, max_file_size, path_name, segment=False):
        self.dir_index = 0
        self.file_index = 0
        self.compress = compress
        self.max_file_size = max_file_size
        self.path_name = path_name
        self.segment = segment
        if sys.version_info[:2] == (3, 3):
            self.isoutdated = False
        else:
            self.isoutdated = True
        self.out_file = self.open_next_file()

    def reserve(self, size):
        cur_file_size = self.out_file.tell()

    def write(self, text):
        if self.segment:
            if self.compress:
                self.out_file.write(text.encode('UTF-8'))
            else:
                self.out_file.write(text)
        else:
            return
        

    def close(self):
        self.out_file.close()

    def open_next_file(self):
        self.file_index = self.file_index
        if self.file_index == 100:
            self.dir_index += 1
            self.file_index = 0
        file_name = 'wiki.txt'
        
        if self.compress:
            if self.isoutdated:
                return bz2.BZ2File('wiki.txt.bz2', 'wb')
            else:
                return bz2.BZ2File('wiki.txt.bz2', 'ab')
        else:
            return open(file_name, 'a',encoding="utf8")

    def dir_name(self):
        ### split into two kinds of directories:
        ### sentences_AA and structure_AA

        prefix = "sentences_" if self.segment else "structure_"

        char1 = self.dir_index % 26
        char2 = self.dir_index / 26 % 26
        return os.path.join(self.path_name, prefix + '%c%c' % (ord('A') + char2, ord('A') + char1))

    def file_name(self):
        return 'wiki_%02d' % self.file_index

### READER #############################################################

tagRE = re.compile(r'(.*?)<(/?\w+)[^>]*>(?:([^<]*)(<.*?>)?)?')

def process_data(ftype, input, output_sentences, output_structure, incubator,
                 vital_titles=None, vital_tags=None):
    global PREFIX
    page = []
    id = None
    inText = False
    redirect = False
    for line in input:
        if ftype != 'xml':
            line = str(line.decode('utf-8'))
        tag = ''
        if '<' in line:
            m = tagRE.search(line)
            if m:
                tag = m.group(2)
        if tag == 'page':
            page = []
            redirect = False
        elif tag == 'id' and not id:
            id = m.group(3)
        elif tag == 'title':
            title = m.group(3)
            if(incubator != ''):
                lang = title.split('/')
        elif tag == 'redirect':
            redirect = True
        elif tag == 'text':
            inText = True
            line = line[m.start(3):m.end(3)] + '\n'
            page.append(line)
            if m.lastindex == 4: # open-close
                inText = False
        elif tag == '/text':
            if m.group(1):
                page.append(m.group(1) + '\n')
            inText = False
        elif inText:
            page.append(line)
        elif tag == '/page':
            colon = title.find(':')
            if (colon < 0 or title[:colon] in ACCEPTED_NAMESPACES) and \
                    not redirect:
                if (not vital_titles) or (title in vital_titles):
                    if((incubator != '') and (lang[1] == incubator) and len(lang) > 2):
                        print(id, lang[2])
                        sys.stdout.flush()
                        tags = vital_tags[title] if vital_tags else []
                        WikiDocumentSentences(output_sentences, id, lang[2], tags,
                                              ''.join(page))
                        #WikiDocument(output_structure, id, title, ''.join(page))
                    elif(incubator == ''):
                        print(id, title)
                        sys.stdout.flush()
                        tags = vital_tags[title] if vital_tags else []
                        WikiDocumentSentences(output_sentences, id, title, tags,
                                              ''.join(page))
                        #WikiDocument(output_structure, id, title, ''.join(page))
            id = None
            page = []
        elif tag == 'base':
            # discover prefix from the xml dump file
            # /mediawiki/siteinfo/base
            base = m.group(3)
            PREFIX = base[:base.rfind("/")]

##def load_vital_titles(vitalfn):
##    """Given the filename for the vital titles list (one title per line, with
##    tags), return a set of Wikipedia titles and a map from those titles to lists
##    of tags."""
##    with open(vitalfn) as infile:
##        titles = set()
##        titles_to_tags = {}
##        for line in infile:
##            line = line.strip()
##            splitted = line.split("|||")
##            title = splitted[0]
##            tags = splitted[1:]
##            titles.add(title)
##            titles_to_tags[title] = tags
##        return titles, titles_to_tags

### CL INTERFACE #########################################################



def show_help():
    print(__doc__, end=' ', file=sys.stdout)

def show_usage(script_name):
    print('Usage: %s [options]' % script_name, file=sys.stderr)

##
# Minimum size of output files
minFileSize = 200 * 1024

def get_argparser():
    """Build the argument parser for main."""
    parser = argparse.ArgumentParser(description='WikiExtractor')
    parser.add_argument('--infn', type=str, required=False, help="The location/file of the Wiki Dump. Supports uncompressed, bz2, and gzip.")
    parser.add_argument('--incubator', type=str, required=False, help="If this is included, WikiExtractor will scramble in Incubator Mode. You should specify language here (e.g enm - Middle English)")
    #parser.add_argument('--vitalfn', type=str, required=False)
    #parser.add_argument('--all-articles',dest='allArticles',action='store_true')
    #parser.add_argument('--structure',dest='keepSections',action='store_true')
    #parser.add_argument('--no-structure',dest='keepSections',action='store_false')
    parser.add_argument('--compress',dest='compress',action='store_true', help="If this is included the output file will be compressed (bz2)")
    #parser.set_defaults(keepSections=True)
    #parser.set_defaults(allArticles=True)
    parser.set_defaults(compress=False)
    parser.set_defaults(incubator='')
    parser.set_defaults(infn='')
    return parser

def main():
    global keepLinks, keepSections, PREFIX, ACCEPTED_NAMESPACES
    script_name = os.path.basename(sys.argv[0])

    parser = get_argparser()
    args = parser.parse_args()
    keepSections = True

    compress = args.compress
    file_size = 500 * 1024
    output_dir = '.'

    if not keepLinks:
        ignoreTag('a')

    vital_titles = None
    vital_tags = None

##    if args.vitalfn:
##        vital_titles, vital_tags = load_vital_titles(args.vitalfn)
##        print("Extracting {0} articles...".format(len(vital_titles)))
##    elif args.allArticles:
##        print("Extracting every article...")
##    else:
##        print("Need either --all-articles or --vitalfn")
##        sys.exit(1)

    output_sentences = OutputSplitter(compress, file_size, output_dir,
                                      segment=True)
    #output_structure = OutputSplitter(compress, file_size, output_dir)

    incubator = args.incubator
    fname = args.infn
    if fname == "":
        parser.print_help()
        print('')
        print("Please include --infn FIlENAME in your command.")
        sys.exit()
    
    ftypes = mimetypes.guess_type(fname)
    if 'bzip2' in ftypes:
        print('File detected as being bzip2.')
        f = bz2.BZ2File(fname, mode='r')
        process_data('bzip2',f, output_sentences, vital_titles, incubator, vital_tags)
        output_sentences.close()
        
    elif 'gzip' in ftypes:
        print('File detected as being a gzip.')
        f = gzip.GzipFile(fname, mode='r')
        process_data('gzip',f, output_sentences, vital_titles, incubator, vital_tags)
        output_sentences.close() 
    else:
        with open(args.infn,encoding="utf8") as infile:
            process_data('xml',infile, output_sentences, vital_titles, incubator, vital_tags)
        output_sentences.close()

    #output_structure.close()


if __name__ == '__main__':
    main()
