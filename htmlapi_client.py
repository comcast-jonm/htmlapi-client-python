#
#   Copyright (C) 2013 Comcast Corporation
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import urllib
import urllib2
import urlparse
from lxml import etree

def _normalize_whitespace(s):
    return ' '.join(s.split())

def _extract_text_help(root, acc):
    if root.text is not None and root.text.strip():
        acc.append(_normalize_whitespace(root.text.strip()))
    for child in root.getchildren():
        acc = _extract_text_help(child, acc)
        if child.tail is not None and child.tail.strip():
            acc.append(_normalize_whitespace(child.tail.strip()))
    return acc

def _extract_text(root):
    return ' '.join(_extract_text_help(root,[]))

def _extract(elt, doc):
    """This function takes a given DOM node 'elt' and attempts to interpret
    it as a Python value of some sort (possibly an object)."""
    if 'itemtype' in elt.attrib or 'itemscope' in elt.attrib:
        return MicrodataObject(elt, doc)
    tag = elt.tag
    if tag == 'a' and 'href' in elt.attrib:
        href = elt.attrib['href']
        if href.startswith('#'):
            target = doc._doc.getroot().find(".//*[@id='%s']" % href[1:])
            if target is not None: return _extract(target, doc)
        else:
            up = urlparse.urlparse(href)
            remote_doc = enter(urlparse.urlunparse((up.scheme, up.netloc, up.path, up.params, up.query, '')))
            if up.fragment:
                target = remote_doc._doc.getroot().find(".//*[@id='%s']" % up.fragment)
                if target is not None: return _extract(target, remote_doc)
            if len(remote_doc.objects) == 1: return remote_doc.objects[0]
            return _extract(remote_doc._doc.getroot(), remote_doc)
    if tag == 'img': return elt.attrib['src']
    return _extract_text(elt)

def _value_of(doc, fragment=''):
    if fragment:
        target = doc._doc.getroot().find(".//*[@id='%s']" % fragment)
        if target is not None: return _extract(target, doc)
    if len(doc.objects) == 1: return doc.objects[0]
    if len(doc.objects) > 0: return doc.objects
    return _extract(doc._doc.getroot(), doc)

class Link(object):
    """Links are basically a representation of HTML <a> tags. The main
    thing you can do with a Link is to follow it."""
    def __init__(self, elt, doc):
        self._elt = elt
        self._doc = doc

    def __repr__(self):
        return "<Link %s at 0x%x>" % (self._elt.attrib['href'], id(self))


    def follow(self):
        href = self._elt.attrib['href']
        resolved = urlparse.urljoin(self._doc._url, href)
        up = urlparse.urlparse(resolved)
        resolved_base = urlparse.urlunparse((up.scheme, up.netloc, up.path,
                                             up.params, up.query, ''))
        if resolved_base == self._doc._url:
            # local
            return _value_of(self._doc, up.fragment)
        else:
            # remote
            remote_doc = enter(resolved_base)
            return _value_of(remote_doc, up.fragment)

class Form(object):
    """Forms are a representation of an HTML <form> tag. Then main thing
    you can do with a form is to 'submit' one by providing a dictionary
    of key-value pairs corresponding to the values to supply to the form's
    <input> elements. N.B. This is not fully implemented per the HTML spec,
    as we only support <input> and not, for example, <textarea> or <select>
    at this point. The other useful thing you can do with a Form is to ask
    it for its .params field, which returns a list of the input names
    provided."""
    def __init__(self, elt, doc):
        self._elt = elt
        self._doc = doc

    def __repr__(self):
        if 'data-rel' not in self._elt.attrib:
            return "<Form at 0x%x>" % id(self)
        return "<Form %s at 0x%x>" % (self._elt.attrib['data-rel'], id(self))

    def _set_value_for(self, elt, args, params):
        if 'name' not in elt.attrib: return
        name = elt.attrib['name']
        if name in args:
            params[name] = args[name]
        else:
            if 'value' in elt.attrib:
                params[name] = elt.attrib['value']
            else:
                params[name] = ""

    def _get_params(self):
        out = []
        for elt in self._elt.findall(".//input"):
            if 'type' in elt.attrib and elt.attrib['type'] == 'hidden':
                continue
            if 'name' in elt.attrib: out.append(elt.attrib['name'])
        return out
    params = property(_get_params)

    def _build_params(self, args):
        params = {}
        for elt in self._elt.findall(".//textarea"):
            self._set_value_for(elt, args, params)
        for elt in self._elt.findall(".//input"):
            self._set_value_for(elt, args, params)
        return urllib.urlencode(params)

    def submit(self, args={}):
        action = urlparse.urljoin(self._doc._url, self._elt.attrib['action'])
        params = self._build_params(args)
        if 'method' not in self._elt.attrib or self._elt.attrib['method'] == 'GET':
            up = urlparse.urlparse(action)
            if up.params: allparams = "%s&%s" % (up.params, params)
            else: allparams = params
            where = urlparse.urlunparse((up.scheme, up.netloc, up.path,
                                         up.params, allparams, ''))
            return enter(where)
        else:
            print "POST", action, "...",
            f = urllib2.urlopen(action, params)
            print "OK"
            return MicrodataDocument(f, action)

class MicrodataObject(object):
    """This represents a particular semantic object, i.e. something identified
    by an @itemscope attribute. MicrodataObjects have several useful properties
    besides their actual semantic @itemprop properties:
      .props = return names of (local) microdata @itemprop properties
      .itemtype = return the @itemtype of this object
      .links = return a list of Link objects contained by this object
      .forms = return a list of Form objects contained by this object
    There is also a shortcut method .submit() that will submit the first
    contained form with the given link relation (as notated by the @data-rel
    attribute)."""
    def __init__(self, root, doc):
        self._root = root
        self._doc = doc
        self._propmap = None
        self._linkmap = None
        self._formmap = None
        self._orphan_forms = None

    def __repr__(self):
        t = self.itemtype
        if t is None: return "<untyped at 0x%x>" % id(self)
        return "<%s at 0x%x>" % (self.itemtype, id(self))

    def _dfs_build_help(self, elt):
        if 'itemprop' in elt.attrib:
            prop = elt.attrib['itemprop']
            if prop not in self._propmap: self._propmap[prop] = []
            self._propmap[prop].append(elt)
            if 'itemscope' in elt.attrib: return
        for child in elt.getchildren():
            self._dfs_build_help(child)

    def _dfs_form_help(self, elt):
        if elt.tag == 'form':
            if 'data-rel' in elt.attrib:
                rel = elt.attrib['data-rel']
                if rel not in self._formmap: self._formmap[rel] = []
                self._formmap[rel].append(Form(elt, self._doc))
            else:
                self._orphan_forms.append(Form(elt, self._doc))
        if 'itemscope' in elt.attrib: return
                
        for child in elt.getchildren():
            self._dfs_form_help(child)

    def _build_formmap(self):
        self._formmap = {}
        self._orphan_forms = []
        for child in self._root.getchildren():
            self._dfs_form_help(child)

    def _dfs_link_help(self, elt):
        if elt.tag == 'a' and 'rel' in elt.attrib:
            rel = elt.attrib['rel']
            if rel not in self._linkmap: self._linkmap[rel] = []
            self._linkmap[rel].append(Link(elt, self._doc))
        if 'itemscope' in elt.attrib: return
        for child in elt.getchildren():
            self._dfs_link_help(child)

    def _build_linkmap(self):
        self._linkmap = {}
        for child in self._root.getchildren():
            self._dfs_link_help(child)

    def _build_propmap(self):
        self._propmap = {}
        for child in self._root.getchildren():
            self._dfs_build_help(child)

    def _get_propmap(self):
        if self._propmap is None: self._build_propmap()
        return self._propmap

    def __len__(self): return self._get_propmap().__len__()
    def __contains__(self,x): return self._get_propmap().__contains__(x)
    def __iter__(self): return self._get_propmap().__iter__()

    def get_property(self, prop, raw=False, allow_multi=True):
        propmap = self._get_propmap()
        if prop not in propmap:
            self_link = self.get_links("self", raw=False, allow_multi=False)
            if self_link is not None:
                alt = self_link.follow()
                if alt is not None and type(alt) == MicrodataObject:
                    return alt.get_property(prop, raw, allow_multi)
            return None
        vals = propmap[prop]
        if not raw:
            vals = map(lambda v : _extract(v, self._doc), vals)
        if len(vals) == 0: return None
        if len(vals) == 1 or not allow_multi: return vals[0]
        return vals

    def get_props(self):
        return self._get_propmap().keys()
    props = property(get_props)

    def get_itemtype(self):
        if 'itemtype' not in self._root.attrib: return None
        return self._root.attrib['itemtype']
    itemtype = property(get_itemtype)

    def _get_linkmap(self):
        if self._linkmap is None: self._build_linkmap()
        return self._linkmap
    links = property(_get_linkmap)

    def _get_formmap(self):
        if self._formmap is None: self._build_formmap()
        return self._formmap
    forms = property(_get_formmap)

    def submit(self, rel, args):
        return self.forms[rel][0].submit(args)

    def get_links(self, rel, raw=False, allow_multi=True):
        linkmap = self._get_linkmap()
        if rel not in linkmap: return None
        links = linkmap[rel]
        if raw:
            return map(lambda l : l._elt, links)
        if len(links) == 0: return None
        if len(links) == 1 or not allow_multi: return links[0]
        return out
    
    def __getitem__(self, name):
        return self.get_property(name, raw=False, allow_multi=False)

    def __getattr__(self, name):
        return self.get_property(name, raw=False, allow_multi=False)

class MicrodataDocument:
    """MicrodataDocuments represent a client application state, usually the
    result of evaluating an entry point via enter(), following a Link, or
    submitting a Form. Useful properties include:
      .forms = return all @data-rel annotated forms
      .allforms = return all <form> elements regardless of annotation
      .links = return all top-level Links (<a> tags, not <link> tags at the
        moment)
      .objects = returns all top-level MicrodataObjects (ones that are not
        enclosed by another MicrodataObject)
    Plus the following convenience methods:
      .follow(rel) = follow the first Link with the given link relation
      .submit(rel, args) = submit the first Form with the given link relation,
        using the 'args' dictionary to supply values for the input elements"""
    def __init__(self, f, url):
        parser = etree.HTMLParser()
        self._doc = etree.parse(f, parser)
        self._url = url

    def _dfs_help(self, root, acc):
        if 'itemtype' in root.attrib and 'itemprop' not in root.attrib:
            acc.append(MicrodataObject(root, self))
            return acc
        for child in root.getchildren():
            acc = self._dfs_help(child, acc)
        return acc

    def _get_forms(self):
        fake_obj = MicrodataObject(self._doc.getroot(), self)
        return fake_obj.forms
    forms = property(_get_forms)

    def _get_links(self):
        fake_obj = MicrodataObject(self._doc.getroot(), self)
        return fake_obj.links
    links = property(_get_links)

    def _get_orphan_forms(self):
        fake_obj = MicrodataObject(self._doc.getroot(), self)
        return fake_obj._orphan_forms
    orphan_forms = property(_get_orphan_forms)

    def _get_all_forms(self):
        return map(lambda elt : Form(elt, self),
                   self._doc.getroot().findall(".//form"))
    allforms = property(_get_all_forms)

    def follow(self, rel):
        return self.links[rel][0].follow()
    
    def submit(self, rel, args):
        return self.forms[rel][0].submit(args)
    
    def get_toplevel_objects(self):
        return self._dfs_help(self._doc.getroot(), [])
    objects = property(get_toplevel_objects)

def enter(url):
    print "GET", url, "...",
    f = urllib2.urlopen(url)
    print "OK"
    return MicrodataDocument(f, url)
