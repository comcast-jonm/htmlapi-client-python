htmlapi-client-python
=====================

This is sample Python code for driving an HTML-based hypermedia API, as
described in Jon Moore's talk: "Building Hypermedia APIs with HTML":

http://www.infoq.com/presentations/web-api-html

As described in that talk, the top-level method of interest is enter(),
where you can supply a URL and arrive at the "start" state of a client
state machine. From there, the client can examine semantic objects
as annotated by HTML5 microdata, for example with ontologies like
Schema.org (http://schema.org/).

In addition, the client can move to new states by calling .follow() on
Link objects or .submit() on Form objects that it discovers.

What's not included?
====================

As this code is largely targeted at driving the demo shown in the talk,
there are several things not implemented that would be necessary for
production use, including a healthy dose of error checking! In particular,
the HTTP subsystem here is not configured to use caching or follow redirects,
although there's nothing that particularly prevents that work from happening.

In addition, the client library does not examine HTTP response codes
nor expose them out to the "application client" that would sit on top.

Patches welcome!

References
==========

* ["Hypermedia APIs: the Rest of REST"](http://vimeo.com/20781278), Øredev 2010. 
* ["Building Hypermedia APIs with HTML"](http://www.infoq.com/presentations/web-api-html), QCon London 2013. 
* [HTML5 Microdata Spec](http://www.whatwg.org/specs/web-apps/current-work/multipage/microdata.html).
* [Schema.org](http://schema.org/).
